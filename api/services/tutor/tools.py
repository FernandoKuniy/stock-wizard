"""The tutor's read-only tools: the only way it can learn a number.

Each tool is bound to one account and reads only that account's money, the same way every
route is scoped through ``get_current_account``. That scoping is what keeps one user's
portfolio out of another's, so it lives right here at each query. The tools reach for the
market layer for prices, news, and profiles, and lean on ``services/analysis`` and the
shared snapshot builder for every figure, so the numbers the tutor quotes are the exact ones
the dashboard shows. The model narrates; it never computes.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Account, Holding, Transaction
from services.analysis.portfolio import (
    position_cost_basis,
    position_gain_loss,
    position_market_value,
)
from services.analysis.risk import concentration, volatility
from services.market.client import CompanyProfile, MarketError, NewsItem, Quote
from services.portfolio import (
    CandleProvider,
    MissingHistory,
    build_history,
    build_snapshot,
)
from services.tutor.glossary import define
from services.tutor.provider import ToolSchema

_CENTS = Decimal("0.01")
_NO_ARGS: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}


class MarketPort(Protocol):
    """The slice of the market client the tools use: quotes, profiles, and news."""

    def get_quote(self, symbol: str) -> Quote: ...
    def get_profile(self, symbol: str) -> CompanyProfile: ...
    def get_company_news(self, symbol: str) -> list[NewsItem]: ...


@dataclass(frozen=True)
class Tool:
    """One tool the model can call: how to describe it, and how to run it."""

    schema: ToolSchema
    run: Callable[[dict[str, Any]], dict[str, Any]]


def build_tools(
    session: Session,
    account: Account,
    market: MarketPort,
    candles: CandleProvider,
    *,
    benchmark_symbol: str = "SPY",
) -> list[Tool]:
    """The tutor's tools, each scoped to ``account`` so it can only read this user's money."""

    def holdings() -> list[Holding]:
        return list(
            session.scalars(
                select(Holding).where(Holding.account_id == account.id).order_by(Holding.symbol)
            )
        )

    def holding(symbol: str) -> Holding | None:
        return session.scalar(
            select(Holding).where(Holding.account_id == account.id, Holding.symbol == symbol)
        )

    def quote(symbol: str) -> Decimal | None:
        try:
            return Decimal(str(market.get_quote(symbol).price))
        except MarketError:
            return None

    def annualized_volatility(symbol: str) -> Decimal | None:
        try:
            closes = [Decimal(str(point.close)) for point in candles.get_candles(symbol).points]
        except MarketError:
            return None
        return volatility(closes)

    def get_portfolio_summary(_args: dict[str, Any]) -> dict[str, Any]:
        snapshot = build_snapshot(
            holdings(), account.cash_balance, account.starting_balance, market
        )
        return {
            "cash": _money(snapshot.cash),
            "starting_balance": _money(snapshot.starting_balance),
            "total_value": _money(snapshot.total_value),
            "total_gain_loss": _money(snapshot.total_gain_loss),
            "total_gain_loss_percent": _money(snapshot.total_gain_loss_percent),
            "cash_weight_percent": _money(snapshot.cash_weight),
            "holdings": [
                {
                    "symbol": view.symbol,
                    "shares": _shares(view.quantity),
                    "market_value": _opt(view.market_value),
                    "weight_percent": _opt(view.weight),
                    "gain_loss": _opt(view.gain_loss),
                    "gain_loss_percent": _opt(view.gain_loss_percent),
                }
                for view in snapshot.holdings
            ],
            "unpriced_symbols": snapshot.unpriced_symbols,
        }

    def get_position_detail(args: dict[str, Any]) -> dict[str, Any]:
        symbol = _symbol(args)
        if not symbol:
            return {"error": "Which stock? Give me a ticker like AAPL."}
        held = holding(symbol)
        if held is None:
            return {"error": f"You don't hold any {symbol} right now."}

        price = quote(symbol)
        detail: dict[str, Any] = {
            "symbol": symbol,
            "shares": _shares(held.quantity),
            "average_cost": _money(held.avg_cost),
            "cost_basis": _money(position_cost_basis(held.quantity, held.avg_cost)),
            "price": _opt(price),
        }
        if price is not None:
            gain_loss = position_gain_loss(held.quantity, held.avg_cost, price)
            detail["market_value"] = _money(position_market_value(held.quantity, price))
            detail["gain_loss"] = _money(gain_loss.absolute)
            detail["gain_loss_percent"] = _money(gain_loss.percent)
        vol = annualized_volatility(symbol)
        if vol is not None:
            detail["annualized_volatility_percent"] = _money(vol)
        return detail

    def get_concentration(_args: dict[str, Any]) -> dict[str, Any]:
        rows = holdings()
        if not rows:
            return {"position_count": 0, "message": "No holdings yet, so nothing to spread out."}
        snapshot = build_snapshot(rows, account.cash_balance, account.starting_balance, market)
        # Value each holding at its live market value, or its cost when the quote failed, so
        # the concentration lines up with the totals the summary reports.
        values = {
            view.symbol: (view.market_value if view.market_value is not None else view.cost_basis)
            for view in snapshot.holdings
        }
        sectors = _sectors(rows, market)
        signal = concentration(values, sectors or None)
        return {
            "position_count": signal.position_count,
            "biggest_position": signal.top_symbol,
            "biggest_position_weight_percent": _money(signal.top_weight),
            "effective_number_of_holdings": _money(signal.effective_holdings),
            "cash_weight_percent": _money(snapshot.cash_weight),
            "sector_weights_percent": {s: _money(w) for s, w in signal.sector_weights.items()},
        }

    def get_benchmark_comparison(_args: dict[str, Any]) -> dict[str, Any]:
        rows = list(
            session.scalars(
                select(Transaction)
                .where(Transaction.account_id == account.id)
                .order_by(Transaction.timestamp)
            )
        )
        try:
            history = build_history(
                rows,
                candles,
                opened_on=account.created_at.date(),
                starting_balance=account.starting_balance,
                benchmark_symbol=benchmark_symbol,
            )
        except MissingHistory:
            return {"error": "I couldn't load the price history to compare against the market."}
        comparison = history.comparison
        if comparison is None:
            return {
                "available": False,
                "message": "The S&P 500 isn't available right now, so I can't compare.",
            }
        return {
            "benchmark": benchmark_symbol,
            "your_value": _money(comparison.portfolio_value),
            "benchmark_value": _money(comparison.benchmark_value),
            "your_return_percent": _money(comparison.portfolio_percent),
            "benchmark_return_percent": _money(comparison.benchmark_percent),
            "difference": _money(comparison.difference),
        }

    def get_recent_news(args: dict[str, Any]) -> dict[str, Any]:
        symbol = _symbol(args)
        if not symbol:
            return {"error": "Which stock's news? Give me a ticker like AAPL."}
        try:
            items = market.get_company_news(symbol)
        except MarketError:
            return {"error": f"Couldn't load news for {symbol} right now."}
        return {
            "symbol": symbol,
            "articles": [
                {
                    "headline": item.headline,
                    "summary": item.summary,
                    "source": item.source,
                    "date": item.date,
                    "url": item.url,
                }
                for item in items
            ],
        }

    def explain_term(args: dict[str, Any]) -> dict[str, Any]:
        term = str(args.get("term", "")).strip()
        if not term:
            return {"error": "Which term should I explain?"}
        definition = define(term)
        if definition is None:
            return {
                "term": term,
                "known": False,
                "message": "Not in the glossary; explain it in your own plain words.",
            }
        return {"term": term, "definition": definition}

    return [
        Tool(
            schema=ToolSchema(
                name="get_portfolio_summary",
                description=(
                    "The user's whole account right now: cash, total value, total gain or loss, "
                    "and every holding with its weight and profit. Call this first when the user "
                    "asks how they're doing, what they own, or how much they've made or lost."
                ),
                parameters=_NO_ARGS,
            ),
            run=get_portfolio_summary,
        ),
        Tool(
            schema=ToolSchema(
                name="get_position_detail",
                description=(
                    "One holding in depth: shares, average cost, current price, profit or loss, "
                    "and how much its price bounces around (annualized volatility). Call this when "
                    "the user asks about a specific stock they own."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "Ticker, e.g. AAPL"}
                    },
                    "required": ["symbol"],
                    "additionalProperties": False,
                },
            ),
            run=get_position_detail,
        ),
        Tool(
            schema=ToolSchema(
                name="get_concentration",
                description=(
                    "How spread out or concentrated the holdings are: number of positions, the "
                    "biggest one's weight, an effective-number-of-holdings figure, cash weight, "
                    "and a sector breakdown. Call this for questions about diversification or the "
                    "risk of betting on one company."
                ),
                parameters=_NO_ARGS,
            ),
            run=get_concentration,
        ),
        Tool(
            schema=ToolSchema(
                name="get_benchmark_comparison",
                description=(
                    "The account against the same money left in the S&P 500: both values, both "
                    "returns, and the dollar difference. Call this when the user asks whether "
                    "they're beating the market or how they compare to just buying the index."
                ),
                parameters=_NO_ARGS,
            ),
            run=get_benchmark_comparison,
        ),
        Tool(
            schema=ToolSchema(
                name="get_recent_news",
                description=(
                    "Recent news headlines for one company. Call this when the user asks why a "
                    "stock moved or what's going on with it. Attribute headlines to their source; "
                    "the numbers inside a headline are the source's, not the user's figures."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "Ticker, e.g. AAPL"}
                    },
                    "required": ["symbol"],
                    "additionalProperties": False,
                },
            ),
            run=get_recent_news,
        ),
        Tool(
            schema=ToolSchema(
                name="explain_term",
                description=(
                    "A plain-English definition of an investing term, in the app's own voice. Call "
                    "this when the user asks what a term means (e.g. 'cost basis', 'volatility')."
                ),
                parameters={
                    "type": "object",
                    "properties": {"term": {"type": "string", "description": "The term to define"}},
                    "required": ["term"],
                    "additionalProperties": False,
                },
            ),
            run=explain_term,
        ),
    ]


def _sectors(rows: Sequence[Holding], market: MarketPort) -> dict[str, str]:
    """Best-effort sector per held symbol; a symbol whose profile fails is simply left out."""
    sectors: dict[str, str] = {}
    for row in rows:
        try:
            sectors[row.symbol] = market.get_profile(row.symbol).industry
        except MarketError:
            continue
    return sectors


def _money(value: Decimal) -> float:
    rounded = float(value.quantize(_CENTS, rounding=ROUND_HALF_UP))
    return rounded if rounded != 0 else 0.0


def _opt(value: Decimal | None) -> float | None:
    return _money(value) if value is not None else None


def _shares(value: Decimal) -> float:
    return float(value)


def _symbol(args: dict[str, Any]) -> str:
    return str(args.get("symbol", "")).strip().upper()
