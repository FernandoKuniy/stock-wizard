"""The time machine: what one lump sum would have done.

Answers the question a beginner actually asks out loud, "what if I'd put $1,000 into this a
year ago?", using the real closing price on the day they'd have bought and the latest close
we have. Still the "numbers" layer: plain deterministic Python, no LLM anywhere near it.

The answer is deliberately paired with the same money left in the index, because on its own
"you'd have made $240" is the kind of figure that reads as a nudge to buy. Next to the S&P
500 it becomes the lesson the whole product is built around: picking one company often
trails just buying the market, and seeing that is the point. Past returns are not a
forecast, and the UI says so plainly.

Nothing here rounds. The API boundary rounds for display, so precision is not lost on the
way (the same rule ``services/portfolio.py`` follows). Shares stay exact fractions too: this
is a hypothetical, not a fill, so rounding a share count down would only introduce an error
the user never actually paid.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from services.analysis.history import Closes

_ZERO = Decimal(0)
_HUNDRED = Decimal(100)


class NotEnoughHistory(Exception):
    """We have no usable close on or after the start date, so there is nothing honest to say."""

    def __init__(self, symbol: str) -> None:
        super().__init__(f"We don't have price history for {symbol} going back that far.")
        self.symbol = symbol


@dataclass(frozen=True)
class WhatIfLeg:
    """One side of the comparison: what the money bought, and what it is worth now."""

    symbol: str
    shares: Decimal
    bought_on: date
    buy_price: Decimal
    latest_on: date
    latest_price: Decimal
    value_now: Decimal
    gain_loss: Decimal
    gain_loss_percent: Decimal


@dataclass(frozen=True)
class WhatIf:
    """A lump sum into one stock, against the same money in the index.

    ``benchmark`` and ``difference`` are ``None`` when the index couldn't be priced. The
    user's own answer still stands on its own; we just can't draw the comparison, which is
    the same treatment the performance chart gives a missing index.
    """

    amount: Decimal
    stock: WhatIfLeg
    benchmark: WhatIfLeg | None
    # Positive means the stock beat the index over the period, in dollars.
    difference: Decimal | None


def what_if(
    amount: Decimal,
    symbol: str,
    closes: Closes,
    *,
    start: date,
    benchmark_symbol: str | None = None,
    benchmark_closes: Closes | None = None,
) -> WhatIf:
    """What ``amount`` put into ``symbol`` on ``start`` would be worth at the latest close.

    Raises ``NotEnoughHistory`` if the stock has no close on or after ``start``: a symbol
    that wasn't trading yet has no honest answer, and guessing one would be worse than
    saying so. A benchmark we can't price is simply left out.
    """
    if amount <= _ZERO:
        raise ValueError("Amount must be greater than zero.")

    stock = _leg(amount, symbol, closes, start)

    benchmark: WhatIfLeg | None = None
    if benchmark_symbol is not None and benchmark_closes:
        try:
            candidate = _leg(amount, benchmark_symbol, benchmark_closes, start)
        except NotEnoughHistory:
            candidate = None
        # Only compare like with like. If the index's first close lands on a different day
        # from the stock's, the two legs cover different windows, and the gap between them
        # would be measuring the calendar rather than the choice. Drop it instead.
        if candidate is not None and candidate.bought_on == stock.bought_on:
            benchmark = candidate

    return WhatIf(
        amount=amount,
        stock=stock,
        benchmark=benchmark,
        difference=stock.value_now - benchmark.value_now if benchmark is not None else None,
    )


def _leg(amount: Decimal, symbol: str, closes: Closes, start: date) -> WhatIfLeg:
    """Buy at the first close on or after ``start``, value it at the most recent one."""
    bought_on, buy_price = _first_close_on_or_after(closes, start, symbol)
    latest_on, latest_price = _latest_close(closes, symbol)

    shares = amount / buy_price
    value_now = shares * latest_price
    gain_loss = value_now - amount

    return WhatIfLeg(
        symbol=symbol,
        shares=shares,
        bought_on=bought_on,
        buy_price=buy_price,
        latest_on=latest_on,
        latest_price=latest_price,
        value_now=value_now,
        gain_loss=gain_loss,
        gain_loss_percent=gain_loss / amount * _HUNDRED,
    )


def _first_close_on_or_after(closes: Closes, start: date, symbol: str) -> tuple[date, Decimal]:
    """The first real close from ``start`` onwards.

    A start date that landed on a weekend or a holiday simply rolls forward to the next day
    the market was open, the same convention the performance chart's date spine uses.
    """
    for day in sorted(closes):
        if day >= start and closes[day] > _ZERO:
            return day, closes[day]
    raise NotEnoughHistory(symbol)


def _latest_close(closes: Closes, symbol: str) -> tuple[date, Decimal]:
    """The most recent real close we hold for this symbol."""
    for day in sorted(closes, reverse=True):
        if closes[day] > _ZERO:
            return day, closes[day]
    raise NotEnoughHistory(symbol)
