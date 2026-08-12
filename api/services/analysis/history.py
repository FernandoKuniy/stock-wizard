"""Portfolio value over time, and how it compares to just buying the S&P 500.

Still the "numbers" layer: plain deterministic Python, no LLM anywhere near it.

We do not store a daily snapshot of what an account was worth. We rebuild it from what
we already know for certain: the transactions, and the real closing price of every
symbol on every day. Replaying those forward gives an exact value for each day, works
from an account's very first day, survives a reset, and needs no new table and no
scheduled job to keep a history table fed.

The benchmark answers the question the whole product is built around: "what if I had
just bought the index instead?" So we take the same starting balance, put all of it
into the S&P 500 on the day the account opened, hold it, and draw that line next to
the user's. Both lines start at exactly the starting balance, which is what makes the
comparison honest.

Looking at a shorter stretch asks the same question from a later day: what the account was
worth when the window opened, all of it into the index on that day, held to now. Both lines
still start at the same number, so the comparison stays honest at any period. See ``trim_to``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

_ZERO = Decimal(0)
_HUNDRED = Decimal(100)
# Cash is rounded the same way the sim rounds it (services/sim/engine.py). Replaying the
# trades with matching rounding means the cash we reconstruct equals the cash actually
# sitting in the account, to the cent, instead of drifting a fraction away from it.
_CASH = Decimal("0.0001")

# Closing prices for one symbol, by day. Days the market was shut are simply absent.
Closes = Mapping[date, Decimal]


@dataclass(frozen=True)
class Trade:
    """One executed trade, as the history math sees it."""

    symbol: str
    side: str  # "buy" or "sell"
    quantity: Decimal
    price: Decimal
    on: date


@dataclass(frozen=True)
class ValuePoint:
    """What something was worth on one day."""

    on: date
    value: Decimal


@dataclass(frozen=True)
class CashCredit:
    """A cash inflow that isn't a trade: a dividend paid into the account, in dollars.

    The amount is absolute (already ``shares * per_share`` at the time it was paid), so the
    replay just adds it to cash on its date, the way a real dividend lands as spendable money.
    """

    on: date
    amount: Decimal


@dataclass(frozen=True)
class SharePayout:
    """A dividend as dollars *per share*, for valuing a fixed position (the benchmark's).

    The benchmark holds a share count we don't know until it's priced, so its dividends are
    carried per-share and multiplied by that count inside ``benchmark_series``.
    """

    on: date
    per_share: Decimal


@dataclass(frozen=True)
class BenchmarkComparison:
    """The punchline: your money against the same money left in the index."""

    portfolio_value: Decimal
    benchmark_value: Decimal
    # Positive means the user is ahead of the index, in dollars.
    difference: Decimal
    portfolio_percent: Decimal
    benchmark_percent: Decimal


def portfolio_value_series(
    starting_balance: Decimal,
    trades: Iterable[Trade],
    closes: Mapping[str, Closes],
    dates: Sequence[date],
    cash_credits: Sequence[CashCredit] = (),
) -> list[ValuePoint]:
    """What the account was worth on each day in ``dates``, oldest first.

    Replays the trades in order, tracking cash and share counts, and prices whatever is
    held at that day's close. A symbol with no bar on a given day is carried at its last
    known close, which is what happens on a holiday or a halted day.

    ``cash_credits`` are non-trade inflows (dividends) added to cash on their date, so the
    reconstructed cash equals what actually sat in the account, dividends included, and the
    line's last point matches the live dashboard total instead of drifting below it.
    """
    ordered = sorted(trades, key=lambda trade: trade.on)
    credits = sorted(cash_credits, key=lambda credit: credit.on)
    prices = {symbol: _carry_forward(bars, dates) for symbol, bars in closes.items()}

    points: list[ValuePoint] = []
    cash = starting_balance
    shares: dict[str, Decimal] = {}
    next_trade = 0
    next_credit = 0

    for day in dates:
        while next_trade < len(ordered) and ordered[next_trade].on <= day:
            trade = ordered[next_trade]
            cash = _apply_to_cash(cash, trade)
            shares[trade.symbol] = _apply_to_shares(shares.get(trade.symbol, _ZERO), trade)
            next_trade += 1
        while next_credit < len(credits) and credits[next_credit].on <= day:
            cash += credits[next_credit].amount
            next_credit += 1

        value = cash
        for symbol, quantity in shares.items():
            if quantity <= _ZERO:
                continue
            price = prices.get(symbol, {}).get(day)
            # No bar at or before this day means the symbol had not started trading yet,
            # which also means we cannot be holding it. Nothing to add.
            if price is not None:
                value += quantity * price
        points.append(ValuePoint(on=day, value=value))

    return points


def benchmark_series(
    starting_balance: Decimal,
    closes: Closes,
    dates: Sequence[date],
    dividends: Sequence[SharePayout] = (),
) -> list[ValuePoint]:
    """What the starting balance would be worth if it had all gone into the index on day one.

    Returns an empty list if the index has no price on the first day, since without it
    there is nothing to buy at and no honest comparison to draw.

    ``dividends`` are the index's own payouts, per share, added as cash so the comparison is
    total return against total return: the user's line collects their holdings' dividends, so a
    price-only index line would quietly flatter them. Only ex-dates strictly after the window's
    first day count, since the position is bought at that day's open and so misses a dividend
    going ex on that very day.
    """
    if not dates:
        return []

    prices = _carry_forward(closes, dates)
    opening_price = prices.get(dates[0])
    if opening_price is None or opening_price <= _ZERO:
        return []

    # Fractional shares, exactly like the app lets a user buy.
    shares = starting_balance / opening_price
    payouts = sorted(
        (payout for payout in dividends if payout.on > dates[0]), key=lambda payout: payout.on
    )

    points: list[ValuePoint] = []
    next_payout = 0
    dividend_cash = _ZERO
    for day in dates:
        while next_payout < len(payouts) and payouts[next_payout].on <= day:
            dividend_cash += shares * payouts[next_payout].per_share
            next_payout += 1
        price = prices.get(day)
        if price is None:
            continue
        points.append(ValuePoint(on=day, value=shares * price + dividend_cash))
    return points


def never_sold_series(
    starting_balance: Decimal,
    trades: Sequence[Trade],
    closes: Mapping[str, Closes],
    dates: Sequence[date],
    cash_credits: Sequence[CashCredit] = (),
) -> list[ValuePoint] | None:
    """What the account would be worth if every buy had simply been held.

    The same replay as ``portfolio_value_series`` with the sells left out, so it reuses that
    machinery rather than repeating it, and it prices off closes the caller has already
    fetched. It answers a fact about the user's own history, not a suggestion: see the copy
    rules in the route that renders it.

    ``cash_credits`` (the account's real dividends) are applied here too so that the difference
    the route shows, real minus never-sold, nets them out: the same dividend dollars sit on both
    sides and cancel, leaving a clean "did selling help?" comparison of the price moves alone.
    This does not re-derive the dividends the counterfactual would have earned on the shares it
    never sold, which keeps a secondary teaching fact from turning into a second dividend engine.

    Returns ``None`` in the two cases where there is no honest answer:

    - **Nothing was ever sold.** The counterfactual is just what already happened, so there
      is nothing to say.
    - **The buys could not have been paid for without a sale's proceeds.** Selling frees cash
      that often funds the next buy; a replay that keeps every buy but drops the sales can
      describe a portfolio the account could never have afforded. Valuing that would be
      inventing a number, so we decline instead, the same instinct that makes the history
      refuse to draw a line it cannot price.
    """
    if not any(trade.side == "sell" for trade in trades):
        return None

    buys = [trade for trade in trades if trade.side == "buy"]
    if not _affordable(starting_balance, buys):
        return None

    return portfolio_value_series(starting_balance, buys, closes, dates, cash_credits)


def _affordable(starting_balance: Decimal, buys: Sequence[Trade]) -> bool:
    """Whether these buys could have been paid for without the proceeds of any sale."""
    cash = starting_balance
    for trade in sorted(buys, key=lambda trade: trade.on):
        cash -= (trade.quantity * trade.price).quantize(_CASH, rounding=ROUND_HALF_UP)
        if cash < _ZERO:
            return False
    return True


def trim_to(points: Sequence[ValuePoint], since: date | None) -> list[ValuePoint]:
    """The stretch of ``points`` from ``since`` onward. All of them when ``since`` is None.

    The series is always rebuilt over the account's whole life first, because a trade made
    before the window still has to be replayed to know what was held during it. Only then is
    it trimmed to the stretch being looked at, which costs nothing: the prices were already
    fetched and cached, so a shorter period is a slice, never another request.
    """
    if since is None:
        return list(points)
    return [point for point in points if point.on >= since]


def compare_to_benchmark(
    baseline: Decimal,
    portfolio: Sequence[ValuePoint],
    benchmark: Sequence[ValuePoint],
) -> BenchmarkComparison | None:
    """Where the two lines ended up, measured from ``baseline``.

    ``baseline`` is what the account was worth when the window opened: the starting balance
    over its whole life, or its value on the first day of a shorter stretch. None if either
    side has nothing to compare.
    """
    if not portfolio or not benchmark or baseline <= _ZERO:
        return None

    portfolio_value = portfolio[-1].value
    benchmark_value = benchmark[-1].value

    return BenchmarkComparison(
        portfolio_value=portfolio_value,
        benchmark_value=benchmark_value,
        difference=portfolio_value - benchmark_value,
        portfolio_percent=(portfolio_value - baseline) / baseline * _HUNDRED,
        benchmark_percent=(benchmark_value - baseline) / baseline * _HUNDRED,
    )


def _apply_to_cash(cash: Decimal, trade: Trade) -> Decimal:
    """Debit a buy, credit a sell."""
    amount = (trade.quantity * trade.price).quantize(_CASH, rounding=ROUND_HALF_UP)
    return cash - amount if trade.side == "buy" else cash + amount


def _apply_to_shares(held: Decimal, trade: Trade) -> Decimal:
    return held + trade.quantity if trade.side == "buy" else held - trade.quantity


def _carry_forward(closes: Closes, dates: Sequence[date]) -> dict[date, Decimal]:
    """Fill in the gaps: every day gets the close of the last day that had one."""
    filled: dict[date, Decimal] = {}
    last: Decimal | None = None
    for day in dates:
        price = closes.get(day)
        if price is not None:
            last = price
        if last is not None:
            filled[day] = last
    return filled
