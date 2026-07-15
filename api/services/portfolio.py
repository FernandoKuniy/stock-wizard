"""One place that turns an account's holdings into the figures the app shows.

The dashboard route and the AI tutor both need the same answer to "what is this account
worth, and how is each position doing?". Computing it in two places invites drift, and
drift in money figures is exactly what the two hard rules exist to prevent. So both call
``build_snapshot`` and read identical numbers off it.

This is a composition layer, not the analysis layer: it reaches into the market client for
live quotes and reads ``Holding`` rows, then leans on the pure functions in
``services/analysis`` for every actual calculation. It never rounds; the API boundary
rounds for display so precision is not lost here. Callers load their own account-scoped
holdings and pass them in, so the "one user can't read another's money" check stays visible
at each call site.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from models import Holding, Transaction
from services.analysis.history import (
    BenchmarkComparison,
    Trade,
    ValuePoint,
    benchmark_series,
    compare_to_benchmark,
    portfolio_value_series,
)
from services.analysis.portfolio import (
    Position,
    portfolio_total_value,
    position_cost_basis,
    position_gain_loss,
    position_market_value,
    position_weights,
    total_gain_loss,
)
from services.market.candles import Candles
from services.market.client import MarketError, Quote

_ZERO = Decimal(0)
_HUNDRED = Decimal(100)
# About two years of daily bars, the whole cached window (see market/candles.py).
HISTORY_OUTPUTSIZE = 500


class MissingHistory(Exception):
    """A held symbol's price history is unavailable, so the series can't be drawn honestly."""

    def __init__(self, symbol: str) -> None:
        super().__init__(f"No price history available for {symbol}.")
        self.symbol = symbol


class QuoteProvider(Protocol):
    """The slice of the market client this layer uses: a latest quote for a symbol."""

    def get_quote(self, symbol: str) -> Quote: ...


class CandleProvider(Protocol):
    """The slice of the candle client this layer uses: daily bars for a symbol."""

    def get_candles(self, symbol: str, *, outputsize: int = ...) -> Candles: ...


@dataclass(frozen=True)
class HoldingView:
    """One holding with its figures computed. Price-derived fields are ``None`` when the
    live quote failed, so a flaky provider reads as "unknown", never as a loss."""

    symbol: str
    quantity: Decimal
    avg_cost: Decimal
    cost_basis: Decimal
    price: Decimal | None
    market_value: Decimal | None
    gain_loss: Decimal | None
    gain_loss_percent: Decimal | None
    weight: Decimal | None


@dataclass(frozen=True)
class PortfolioSnapshot:
    """Everything the dashboard and the tutor say about an account, before rounding."""

    cash: Decimal
    starting_balance: Decimal
    total_value: Decimal
    total_cost_basis: Decimal
    total_gain_loss: Decimal
    total_gain_loss_percent: Decimal
    cash_weight: Decimal
    holdings: list[HoldingView]
    # Symbols we couldn't get a live quote for. They're carried in the totals at cost (see
    # below) and flagged here so the caller can be honest that the figure is a little stale.
    unpriced_symbols: list[str]


def build_snapshot(
    holdings: Sequence[Holding],
    cash: Decimal,
    starting_balance: Decimal,
    market: QuoteProvider,
) -> PortfolioSnapshot:
    """Value an account: fetch each holding's quote, then compute the totals in code.

    A holding whose quote fails is carried in the totals at what it cost, rather than
    dropped, so one flaky quote can't shrink the portfolio and read as a loss the user never
    took. That holding's own row still shows ``price=None`` so the UI can say it's stale.
    """
    quoted: dict[str, Decimal] = {}
    unpriced: list[str] = []
    for holding in holdings:
        try:
            quoted[holding.symbol] = Decimal(str(market.get_quote(holding.symbol).price))
        except MarketError:
            unpriced.append(holding.symbol)

    for_totals = dict(quoted)
    for holding in holdings:
        if holding.symbol in unpriced:
            for_totals[holding.symbol] = holding.avg_cost

    positions = [Position(h.symbol, h.quantity, h.avg_cost) for h in holdings]
    total_value = portfolio_total_value(cash, positions, for_totals)
    gain_loss = total_gain_loss(cash, starting_balance, positions, for_totals)
    weights = position_weights(cash, positions, for_totals)

    total_cost_basis = _ZERO
    for holding in holdings:
        total_cost_basis += position_cost_basis(holding.quantity, holding.avg_cost)
    cash_weight = cash / total_value * _HUNDRED if total_value > _ZERO else _ZERO

    return PortfolioSnapshot(
        cash=cash,
        starting_balance=starting_balance,
        total_value=total_value,
        total_cost_basis=total_cost_basis,
        total_gain_loss=gain_loss.absolute,
        total_gain_loss_percent=gain_loss.percent,
        cash_weight=cash_weight,
        holdings=[_holding_view(h, quoted, weights) for h in holdings],
        unpriced_symbols=unpriced,
    )


def _holding_view(
    holding: Holding, prices: dict[str, Decimal], weights: dict[str, Decimal]
) -> HoldingView:
    cost_basis = position_cost_basis(holding.quantity, holding.avg_cost)
    price = prices.get(holding.symbol)
    if price is None:
        return HoldingView(
            symbol=holding.symbol,
            quantity=holding.quantity,
            avg_cost=holding.avg_cost,
            cost_basis=cost_basis,
            price=None,
            market_value=None,
            gain_loss=None,
            gain_loss_percent=None,
            weight=None,
        )
    gain_loss = position_gain_loss(holding.quantity, holding.avg_cost, price)
    return HoldingView(
        symbol=holding.symbol,
        quantity=holding.quantity,
        avg_cost=holding.avg_cost,
        cost_basis=cost_basis,
        price=price,
        market_value=position_market_value(holding.quantity, price),
        gain_loss=gain_loss.absolute,
        gain_loss_percent=gain_loss.percent,
        weight=weights.get(holding.symbol, _ZERO),
    )


@dataclass(frozen=True)
class HistoryResult:
    """The performance series and its punchline, computed from transactions plus real closes.

    ``benchmark_symbol`` is ``None`` when the index couldn't be loaded (the user's own line is
    still correct on its own). ``comparison`` is ``None`` when there is nothing to compare.
    """

    benchmark_symbol: str | None
    portfolio: list[ValuePoint]
    benchmark: list[ValuePoint]
    comparison: BenchmarkComparison | None


def build_history(
    transactions: Sequence[Transaction],
    candles: CandleProvider,
    *,
    opened_on: date,
    starting_balance: Decimal,
    benchmark_symbol: str,
    outputsize: int = HISTORY_OUTPUTSIZE,
) -> HistoryResult:
    """Rebuild what an account has been worth over time, against the same money left in the index.

    The math is the pure functions in ``services/analysis/history``, so this figure is identical
    to the one the dashboard chart draws. The two failure modes get deliberately opposite
    treatment: if a *held* symbol's history is missing we raise ``MissingHistory`` (a chart that
    silently drops a position understates someone's money), but if only the *index* is missing we
    still return the user's own line and leave the comparison empty.
    """
    trades = [
        Trade(
            symbol=row.symbol,
            side=row.side,
            quantity=row.quantity,
            price=row.price,
            on=row.timestamp.date(),
        )
        for row in transactions
    ]

    # Every symbol the account ever touched, not just what it holds now: a stock sold last
    # month still has to be priced on the days it was held.
    closes: dict[str, dict[date, Decimal]] = {}
    for symbol in sorted({trade.symbol for trade in trades}):
        try:
            closes[symbol] = _closes(candles.get_candles(symbol, outputsize=outputsize))
        except MarketError as exc:
            raise MissingHistory(symbol) from exc

    try:
        benchmark_closes = _closes(candles.get_candles(benchmark_symbol, outputsize=outputsize))
    except MarketError:
        benchmark_closes = {}  # the user's own line is still correct; we just can't compare

    dates = _trading_days(opened_on, benchmark_closes, closes)
    portfolio = portfolio_value_series(starting_balance, trades, closes, dates)
    benchmark = benchmark_series(starting_balance, benchmark_closes, dates)
    comparison = compare_to_benchmark(starting_balance, portfolio, benchmark)

    return HistoryResult(
        benchmark_symbol=benchmark_symbol if benchmark else None,
        portfolio=portfolio,
        benchmark=benchmark,
        comparison=comparison,
    )


def _closes(candles: Candles) -> dict[date, Decimal]:
    """A symbol's daily closes, keyed by day, as exact Decimals for the analysis layer."""
    return {date.fromisoformat(p.date): Decimal(str(p.close)) for p in candles.points}


def _trading_days(
    opened_on: date,
    benchmark_closes: dict[date, Decimal],
    closes: dict[str, dict[date, Decimal]],
) -> list[date]:
    """The days the chart has a point for: every market day since the account opened.

    The index's own trading days are the natural calendar, since it trades whenever the US
    market is open. If we couldn't fetch it, fall back to the days the held symbols traded, and
    failing even that, to the single day the account opened.
    """
    if benchmark_closes:
        days = sorted(day for day in benchmark_closes if day >= opened_on)
    else:
        days = sorted({day for bars in closes.values() for day in bars if day >= opened_on})
    return days or [opened_on]
