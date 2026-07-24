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

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from models import Holding, Transaction
from services.analysis.checkup import Finding, PortfolioFacts
from services.analysis.checkup import evaluate as evaluate_checkup
from services.analysis.history import (
    BenchmarkComparison,
    Trade,
    ValuePoint,
    benchmark_series,
    compare_to_benchmark,
    portfolio_value_series,
    trim_to,
)
from services.analysis.movers import Mover, what_moved
from services.analysis.portfolio import (
    Position,
    portfolio_total_value,
    position_cost_basis,
    position_gain_loss,
    position_market_value,
    position_weights,
    total_gain_loss,
)
from services.analysis.risk import concentration
from services.analysis.whatif import WhatIf, what_if
from services.market.candles import Candles
from services.market.client import CompanyProfile, MarketError, Quote

_ZERO = Decimal(0)
_HUNDRED = Decimal(100)
# What risk.py buckets a symbol under when its sector couldn't be looked up.
_UNKNOWN_SECTOR = "Unknown"
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


class ProfileProvider(Protocol):
    """The slice of the market client this layer uses for sectors: a company profile."""

    def get_profile(self, symbol: str) -> CompanyProfile: ...


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
    # One sentence naming which position is behind the movement, or None when nothing has
    # moved. Unrealized only, so it describes what's held now and never claims to explain the
    # account's total gain (see services/analysis/movers.py).
    what_moved: str | None


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
    views = [_holding_view(h, quoted, weights) for h in holdings]

    return PortfolioSnapshot(
        cash=cash,
        starting_balance=starting_balance,
        total_value=total_value,
        total_cost_basis=total_cost_basis,
        total_gain_loss=gain_loss.absolute,
        total_gain_loss_percent=gain_loss.percent,
        cash_weight=cash_weight,
        holdings=views,
        unpriced_symbols=unpriced,
        what_moved=what_moved([Mover(v.symbol, v.gain_loss) for v in views]),
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
    ``baseline`` is what the account was worth when this window opened, which is where both
    lines start.
    """

    benchmark_symbol: str | None
    baseline: Decimal
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
    since: date | None = None,
    outputsize: int = HISTORY_OUTPUTSIZE,
) -> HistoryResult:
    """Rebuild what an account has been worth over time, against the same money left in the index.

    The math is the pure functions in ``services/analysis/history``, so this figure is identical
    to the one the dashboard chart draws. The two failure modes get deliberately opposite
    treatment: if a *held* symbol's history is missing we raise ``MissingHistory`` (a chart that
    silently drops a position understates someone's money), but if only the *index* is missing we
    still return the user's own line and leave the comparison empty.

    ``since`` narrows the answer to one stretch (the chart's period selector). It is a slice of
    a series we build over the account's whole life either way, so a shorter period costs no
    extra provider call. The index leg is rebought at the window's opening value, so both lines
    still start at the same number.
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
    full = portfolio_value_series(starting_balance, trades, closes, dates)
    portfolio = trim_to(full, since)
    window = [point.on for point in portfolio]

    # Over the account's whole life the baseline is the money it opened with, which is what
    # makes both lines start at exactly the same number. Over a shorter stretch it is whatever
    # the account was worth on that stretch's first day: the same question asked from a later
    # day. Asking for a year on a three-day-old account is its whole life, so it takes the
    # starting balance too.
    full_window = len(portfolio) == len(full)
    baseline = starting_balance if full_window or not portfolio else portfolio[0].value

    benchmark = benchmark_series(baseline, benchmark_closes, window)
    comparison = compare_to_benchmark(baseline, portfolio, benchmark)

    return HistoryResult(
        benchmark_symbol=benchmark_symbol if benchmark else None,
        baseline=baseline,
        portfolio=portfolio,
        benchmark=benchmark,
        comparison=comparison,
    )


def build_what_if(
    candles: CandleProvider,
    symbol: str,
    amount: Decimal,
    *,
    start: date,
    benchmark_symbol: str,
    outputsize: int = HISTORY_OUTPUTSIZE,
) -> WhatIf:
    """What a lump sum into ``symbol`` on ``start`` would be worth now, against the index.

    Reuses the same cached candle window the price chart already fetched, so asking this on
    a stock page usually costs no provider call at all. If the index can't be loaded we
    still answer the user's question and just drop the comparison, the same asymmetry
    ``build_history`` uses.
    """
    try:
        closes = _closes(candles.get_candles(symbol, outputsize=outputsize))
    except MarketError as exc:
        raise MissingHistory(symbol) from exc

    try:
        benchmark_closes = _closes(candles.get_candles(benchmark_symbol, outputsize=outputsize))
    except MarketError:
        benchmark_closes = {}

    return what_if(
        amount,
        symbol.upper(),
        closes,
        start=start,
        benchmark_symbol=benchmark_symbol,
        benchmark_closes=benchmark_closes,
    )


def build_sectors(symbols: Iterable[str], market: ProfileProvider) -> dict[str, str]:
    """Best-effort sector per symbol. One whose profile lookup fails is simply left out.

    Profiles are cached for a day in the market layer, so across all users this costs about
    one call per symbol per day. Callers still only ask for symbols someone is actually
    looking at, per the "never poll the whole universe" rule.
    """
    sectors: dict[str, str] = {}
    for symbol in symbols:
        try:
            sectors[symbol] = market.get_profile(symbol).industry
        except MarketError:
            continue
    return sectors


def build_checkup(snapshot: PortfolioSnapshot, sectors: Mapping[str, str]) -> list[Finding]:
    """Run the portfolio check-up over a snapshot that has already been built.

    Reads no market data of its own: the values come from the snapshot the caller is already
    holding, and ``sectors`` is whatever ``build_sectors`` managed to look up (empty is fine,
    the sector check then reports that it doesn't know). The actual judgement is the pure code
    in ``services/analysis/checkup.py``; all this does is shape the facts for it.
    """
    # Value each holding the way the totals do: at its live market value, or at what it cost
    # when the quote failed. Otherwise a flaky provider would quietly change the weights.
    values = {
        view.symbol: (view.market_value if view.market_value is not None else view.cost_basis)
        for view in snapshot.holdings
    }
    signal = concentration(values, sectors or None)

    top_sector: str | None = None
    top_sector_weight = _ZERO
    if signal.sector_weights:
        top_sector = max(signal.sector_weights, key=lambda name: signal.sector_weights[name])
        top_sector_weight = signal.sector_weights[top_sector]
        # "Unknown" is the bucket for symbols we couldn't label. If that is the biggest group
        # we know less than we know, so report not-knowing rather than naming it as a sector.
        if top_sector == _UNKNOWN_SECTOR:
            top_sector = None
            top_sector_weight = _ZERO

    return evaluate_checkup(
        PortfolioFacts(
            position_count=signal.position_count,
            top_symbol=signal.top_symbol,
            top_weight=signal.top_weight,
            effective_holdings=signal.effective_holdings,
            cash_weight=snapshot.cash_weight,
            top_sector=top_sector,
            top_sector_weight=top_sector_weight,
        )
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
