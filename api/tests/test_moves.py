"""Unit tests for the big-move note.

A pure function over one figure, so the threshold and the wording are both checked exactly.
The copy is part of the contract: this may say a move is unusual, but it may never say what
caused it, and it may never suggest doing anything about it.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from services.analysis.moves import BIG_MOVE_PERCENT, biggest_moves, describe_day_move


def d(value: str) -> Decimal:
    return Decimal(value)


def test_an_ordinary_day_says_nothing() -> None:
    # A price wobbling a percent or two is a price wobbling. Remarking on it would teach
    # someone to read noise as news.
    assert describe_day_move("AAPL", d("1.4")) is None
    assert describe_day_move("AAPL", d("-2.9")) is None
    assert describe_day_move("AAPL", d("0")) is None


def test_a_big_day_up_is_named() -> None:
    assert describe_day_move("AAPL", d("7.2")) == (
        "AAPL is up 7.2% today, which is a big day for one stock."
    )


def test_a_big_day_down_is_named() -> None:
    assert describe_day_move("NVDA", d("-8.5")) == (
        "NVDA is down 8.5% today, which is a big day for one stock."
    )


def test_the_threshold_is_inclusive_in_both_directions() -> None:
    assert describe_day_move("AAPL", BIG_MOVE_PERCENT) is not None
    assert describe_day_move("AAPL", -BIG_MOVE_PERCENT) is not None
    assert describe_day_move("AAPL", BIG_MOVE_PERCENT - d("0.01")) is None
    assert describe_day_move("AAPL", -BIG_MOVE_PERCENT + d("0.01")) is None


def test_the_size_is_rounded_to_one_decimal() -> None:
    # "down 7.24999%" is noise in a sentence, and the sign is a word so there is no bare minus.
    result = describe_day_move("AAPL", d("-7.249"))

    assert result is not None
    assert "down 7.2%" in result
    assert "-" not in result


def test_the_note_never_claims_a_cause_or_suggests_an_action() -> None:
    """Both hard rules, asserted rather than trusted.

    Most one-day moves have no clean explanation. Saying "because" would teach a beginner to
    see patterns that aren't there, and saying "buy the dip" would be advice.
    """
    banned = ("because", "due to", "caused", "why", "buy", "sell", "you should", "opportunity")
    for change in (d("7.2"), d("-8.5"), d("42"), d("-99")):
        result = describe_day_move("AAPL", change)
        assert result is not None
        for phrase in banned:
            assert phrase not in result.lower(), f"drifted: {phrase!r} in {result!r}"


# Five consecutive trading days with a big jump, a big drop, and two quiet days.
WEEK = [date(2026, 3, 2), date(2026, 3, 3), date(2026, 3, 4), date(2026, 3, 5), date(2026, 3, 6)]


def series(*prices: str) -> dict[date, Decimal]:
    return {day: Decimal(price) for day, price in zip(WEEK, prices, strict=True)}


def test_a_single_close_has_nothing_to_move_against() -> None:
    assert biggest_moves({WEEK[0]: Decimal("100")}) is None
    assert biggest_moves({}) is None


def test_the_biggest_days_are_picked_out() -> None:
    # 100 -> 110 (+10%) -> 99 (-10%) -> 100 (+1.01%) -> 101 (+1%)
    result = biggest_moves(series("100", "110", "99", "100", "101"))
    assert result is not None

    # Four days moved (the first close has no day before it to compare against).
    assert result.trading_days == 4
    assert [move.on for move in result.up[:1]] == [WEEK[1]]
    assert [move.on for move in result.down[:1]] == [WEEK[2]]
    assert result.up[0].percent_change == Decimal("10")
    assert result.up[0].close == Decimal("110")


def test_a_stock_that_only_rose_has_no_down_days() -> None:
    result = biggest_moves(series("100", "110", "120", "130", "140"))
    assert result is not None

    # Padding the list with flat or positive days would be inventing a story.
    assert result.down == []
    assert len(result.up) == 3


def test_a_stock_that_only_fell_has_no_up_days() -> None:
    result = biggest_moves(series("140", "130", "120", "110", "100"))
    assert result is not None

    assert result.up == []
    assert len(result.down) == 3


def test_a_bad_close_is_skipped_rather_than_producing_nonsense() -> None:
    closes = series("100", "110", "0", "120", "130")

    result = biggest_moves(closes)
    assert result is not None

    # The zero close is dropped, so the days either side compare directly rather than
    # producing a -100% and a division that means nothing.
    assert all(move.close > Decimal("0") for move in result.up + result.down)
    assert result.trading_days == 3


def test_the_count_is_configurable() -> None:
    result = biggest_moves(series("100", "110", "99", "100", "101"), count=1)
    assert result is not None

    assert len(result.up) == 1
    assert len(result.down) == 1
