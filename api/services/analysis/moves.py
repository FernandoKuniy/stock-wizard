"""Notable price moves: when a day is unusual enough to be worth explaining.

Still the analysis layer, so still plain Python with no LLM anywhere near it. The product spec
has always asked for "a one-line 'why did this move?' on big price changes, pulled from news",
and this is the half of it that decides **when** to say something. The headlines themselves are
the provider's words, fetched separately and attributed to their source.

The distinction matters for both hard rules. The threshold and the sentence are code, so the
figure in "AAPL is down 7.2% today" is one the analysis layer worked out. And the copy
deliberately **never claims causation**: it says the move is unusual and that here is what was
in the news, not that the news is the reason. Most one-day moves have no clean explanation, and
teaching a beginner to reach for one is teaching them to see patterns that aren't there.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from services.analysis.history import Closes

_ZERO = Decimal(0)
_HUNDRED = Decimal(100)
_TENTH = Decimal("0.1")

# How many days to show on each side of the biggest-moves list. Three is enough to make the
# point that a year's movement lands on a handful of days, and short enough to read.
BIGGEST_MOVES = 3

# A one-day move of at least this size in either direction is unusual enough for a single
# stock to be worth pointing at. Below it, a price wobbling around is just a price wobbling
# around, and remarking on it would teach someone to read noise as news.
BIG_MOVE_PERCENT = Decimal(5)


def describe_day_move(symbol: str, percent_change: Decimal) -> str | None:
    """One sentence when today's move is big enough to be worth a look, else ``None``.

    Pure and total: the same figure always gives the same sentence, and it never reads a
    clock, a database or a price of its own.
    """
    if abs(percent_change) < BIG_MOVE_PERCENT:
        return None

    direction = "up" if percent_change > _ZERO else "down"
    size = abs(percent_change).quantize(_TENTH, rounding=ROUND_HALF_UP)
    return f"{symbol} is {direction} {size}% today, which is a big day for one stock."


@dataclass(frozen=True)
class DayMove:
    """One trading day and how far the price moved on it, against the day before."""

    on: date
    percent_change: Decimal
    close: Decimal


@dataclass(frozen=True)
class BiggestMoves:
    """The handful of days that did most of the work, out of every day in the window.

    ``trading_days`` is how many days had a move at all, which is the number that makes the
    point: a year's worth of movement tends to land on a few of them.
    """

    trading_days: int
    up: list[DayMove]
    down: list[DayMove]


def biggest_moves(closes: Closes, *, count: int = BIGGEST_MOVES) -> BiggestMoves | None:
    """The biggest up days and the biggest down days in a price series.

    Each day's move is measured against the previous close we hold, which is the same
    convention ``risk.daily_returns`` uses. A day whose previous close is zero or negative is
    skipped rather than producing a nonsense percentage.

    Returns ``None`` when there are fewer than two usable closes, since a single price has
    nothing to move against. Ties break on the date, newest first, so the list is stable.
    """
    days = sorted(day for day in closes if closes[day] > _ZERO)
    if len(days) < 2:
        return None

    moves = [
        DayMove(
            on=today,
            percent_change=(closes[today] - closes[before]) / closes[before] * _HUNDRED,
            close=closes[today],
        )
        for before, today in zip(days, days[1:], strict=False)
    ]
    if not moves:
        return None

    up = sorted(moves, key=lambda move: (-move.percent_change, -move.on.toordinal()))
    down = sorted(moves, key=lambda move: (move.percent_change, -move.on.toordinal()))

    return BiggestMoves(
        trading_days=len(moves),
        # Only days that actually went that way. A stock that never fell has no down days,
        # and padding the list with flat or positive days would be inventing a story.
        up=[move for move in up[:count] if move.percent_change > _ZERO],
        down=[move for move in down[:count] if move.percent_change < _ZERO],
    )
