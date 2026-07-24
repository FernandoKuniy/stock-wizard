"""Unit tests for the big-move note.

A pure function over one figure, so the threshold and the wording are both checked exactly.
The copy is part of the contract: this may say a move is unusual, but it may never say what
caused it, and it may never suggest doing anything about it.
"""

from __future__ import annotations

from decimal import Decimal

from services.analysis.moves import BIG_MOVE_PERCENT, describe_day_move


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
