"""Achievements: the deterministic facts about an account that earn a badge.

Still the analysis layer, so still plain Python with no LLM anywhere near it. This is
hard rule #1 applied to a teaching feature: the *fact* that earns a badge (you hold five
different companies, you've held something a year, you sat through a 20% drop) is computed
here in code. The words on the badge are static copy in ``CATALOG``, written by a person.
The model never decides who earned what.

What we reward is deliberately narrow (see docs/decisions.md). We reward **understanding
and good habits**, never activity and never outcomes:

- Rewarding trades placed or days visited would push people to trade and check more, which
  is the exact behaviour the benchmark chart exists to warn against.
- Rewarding profit ("you beat the market this month") rewards luck and teaches a beginner
  to read a month of noise as skill, the precise mistake the whole app is countering.

So every badge here is a habit whose underlying finance is settled: diversification, time in
the market, and not panic-selling a dip. Each is named for the fact it marks, not for praise,
and most can only be earned once, so none of them creates ongoing pressure to do anything.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

_ZERO = Decimal(0)

# Holding thresholds, in calendar days, and the badge each one earns. This is the "streak"
# in this app: the only streak that lines up with good outcomes is how long you leave a
# position alone, and unlike a daily-visit streak it can't be broken by not showing up. The
# day counts match the what-if periods (six months = 182, a year = 365) so the app is
# consistent about what those words mean.
HOLD_TIERS: tuple[tuple[int, str], ...] = (
    (30, "held_one_month"),
    (90, "held_three_months"),
    (182, "held_six_months"),
    (365, "held_one_year"),
)

# Diversification: holding this many different companies at once.
FIVE_COMPANIES = 5

# Held through a dip: down at least this much on a position you've held at least this long,
# and still holding it. The minimum hold keeps a stock that simply opened down on day one
# from counting; the loss floor is measured against your own cost basis, so this only catches
# drops below what you paid (a stock that ran up then fell back is missed, which is the honest
# limit of doing this without a second candle fetch: see docs/architecture.md).
DIP_MIN_DAYS = 30
DIP_LOSS_PERCENT = Decimal(-15)


@dataclass(frozen=True)
class Fill:
    """One dated change to a position: a buy adds shares, a sell removes them.

    The narrow shape the hold-duration math needs, with no price and no symbol (the caller
    groups these by symbol already). ``side`` is ``"buy"`` or ``"sell"``.
    """

    on: date
    side: str
    quantity: Decimal


@dataclass(frozen=True)
class PositionFact:
    """One currently-held position, reduced to just what the predicates look at.

    ``held_days`` is how long this position has been held **continuously** (a sell-to-zero
    and later re-buy starts the clock over). ``gain_loss_percent`` is ``None`` when the live
    quote was unavailable, so a flaky provider never accidentally trips the dip badge.
    """

    symbol: str
    held_days: int
    gain_loss_percent: Decimal | None


@dataclass(frozen=True)
class AccountFacts:
    """Everything the predicates need about an account, and nothing else."""

    positions: tuple[PositionFact, ...]


@dataclass(frozen=True)
class Badge:
    """The static description of one achievement: the fact that earns it, and the lesson.

    ``requirement`` is the short "here's how you get it" line, shown even on a locked badge.
    ``lesson`` is the teaching paragraph, the actual point of the whole feature. Neither is
    ever generated: the model narrates the portfolio, not the badges.
    """

    key: str
    title: str
    requirement: str
    lesson: str


# The whole set, in display order: diversification, then the time-in-market ladder, then the
# dip. The copy is named for the fact, never the praise ("Spread across five companies", not
# "Well diversified!"), because praising a choice edges toward telling someone it was the
# right one, and this app teaches, it doesn't advise (hard rule #2).
CATALOG: tuple[Badge, ...] = (
    Badge(
        key="five_companies",
        title="Spread across five companies",
        requirement="Hold 5 different stocks at once",
        lesson=(
            "You own five different companies, so no single one having a bad day can wreck "
            "your whole portfolio. That's diversification, and it's about the closest thing "
            "to a free lunch in investing: you smooth out the wild swings without giving up "
            "much in the long run."
        ),
    ),
    Badge(
        key="held_one_month",
        title="Held for a month",
        requirement="Hold a stock for 30 days",
        lesson=(
            "You've held something for a month without bailing. Doing nothing is a real skill "
            "here. Study after study finds the people who trade the least tend to beat the "
            "people who trade the most."
        ),
    ),
    Badge(
        key="held_three_months",
        title="Held for three months",
        requirement="Hold a stock for 3 months",
        lesson=(
            "Three months in. Prices jump around every single day, but the story that actually "
            "matters plays out over months and years, not hours. You're starting to watch on "
            "the timescale that counts."
        ),
    ),
    Badge(
        key="held_six_months",
        title="Held for six months",
        requirement="Hold a stock for 6 months",
        lesson=(
            "Half a year holding the same stock. This is where compounding gets room to work. "
            "Patience isn't exciting, but it's the thing quietly doing the heavy lifting."
        ),
    ),
    Badge(
        key="held_one_year",
        title="Held for a year",
        requirement="Hold a stock for a year",
        lesson=(
            "A full year. Most people can't sit still this long, which is exactly why sitting "
            "still is an edge. Time in the market beats trying to time the market."
        ),
    ),
    Badge(
        key="held_through_a_dip",
        title="Held through a rough patch",
        requirement="Stay in a stock that's down 15% or more after holding it a month",
        lesson=(
            "Something you owned dropped hard and you didn't jump out. That's genuinely tough, "
            "because selling feels safest right when things look worst, and that's usually when "
            "beginners sell and lock the loss in. Noticing you can sit through it is worth a "
            "lot. (To be clear, selling is sometimes the right call too. This isn't a rule, "
            "just a habit worth spotting in yourself.)"
        ),
    ),
)


def continuous_hold_days(fills: Sequence[Fill], as_of: date) -> int | None:
    """How many days a position has been held **continuously**, as of ``as_of``.

    Walk the fills oldest first, tracking the running share count. A buy while flat starts a
    new hold; more buys on top don't move the start. Any time a sell takes the count back to
    zero the hold is broken, and a later buy begins a fresh one. So selling out and re-buying
    resets the clock, which is the honest reading of "how long have you held this?".

    Returns ``None`` when nothing is held now, so a caller can tell "sold it" apart from
    "held zero days". Same-day fills keep their given order (the sort is stable), so a
    caller passing transactions in time order gets an intraday buy-then-sell right.
    """
    running = _ZERO
    start: date | None = None
    for fill in sorted(fills, key=lambda f: f.on):
        if fill.side == "buy":
            if running <= _ZERO:
                start = fill.on
            running += fill.quantity
        else:
            running -= fill.quantity
            if running <= _ZERO:
                running = _ZERO
                start = None
    if start is None:
        return None
    return (as_of - start).days


def evaluate(facts: AccountFacts) -> set[str]:
    """The badge keys an account has earned, from its facts alone.

    Pure and total: given the same facts it always returns the same keys, and it never reads
    a clock, a database, or a price. Awarding (writing rows, never taking them away) happens
    one layer up, in ``services/achievements.py``.
    """
    earned: set[str] = set()

    if len(facts.positions) >= FIVE_COMPANIES:
        earned.add("five_companies")

    longest = max((position.held_days for position in facts.positions), default=0)
    for days, key in HOLD_TIERS:
        if longest >= days:
            earned.add(key)

    if any(
        position.held_days >= DIP_MIN_DAYS
        and position.gain_loss_percent is not None
        and position.gain_loss_percent <= DIP_LOSS_PERCENT
        for position in facts.positions
    ):
        earned.add("held_through_a_dip")

    return earned
