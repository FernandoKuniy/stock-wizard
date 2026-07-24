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

from decimal import ROUND_HALF_UP, Decimal

_ZERO = Decimal(0)
_TENTH = Decimal("0.1")

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
