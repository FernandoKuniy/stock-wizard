"""Unit tests for "what moved your money".

Pure functions over made-up positions, so the ranking and the wording are both checked
exactly, with no network and no database. The copy is part of the contract here: this
sentence must never claim to explain the account's total gain (it only knows about
unrealized profit on what's held now), and it must never suggest doing anything.
"""

from __future__ import annotations

from decimal import Decimal

from services.analysis.movers import Mover, rank, what_moved


def d(value: str) -> Decimal:
    return Decimal(value)


def test_nothing_held_says_nothing() -> None:
    assert what_moved([]) is None


def test_a_flat_position_has_not_moved() -> None:
    # Exactly break-even is not a story, so there is nothing to say about it.
    assert what_moved([Mover("AAPL", d("0"))]) is None


def test_an_unpriced_position_is_left_out_rather_than_counted_as_flat() -> None:
    # A failed quote means we don't know, which is not the same as "went nowhere".
    assert what_moved([Mover("AAPL", None)]) is None
    assert rank([Mover("AAPL", None), Mover("MSFT", d("50"))]) == [Mover("MSFT", d("50"))]


def test_ranking_is_by_size_in_either_direction() -> None:
    ranked = rank(
        [
            Mover("AAPL", d("100")),
            Mover("NVDA", d("-900")),
            Mover("MSFT", d("400")),
        ]
    )

    # The biggest loss outranks a smaller gain: the question is what moved, not what won.
    assert [mover.symbol for mover in ranked] == ["NVDA", "MSFT", "AAPL"]


def test_ties_break_on_the_symbol_so_the_sentence_is_stable() -> None:
    ranked = rank([Mover("ZM", d("100")), Mover("AAPL", d("-100"))])

    assert [mover.symbol for mover in ranked] == ["AAPL", "ZM"]


def test_a_single_mover_is_named_as_the_only_one() -> None:
    result = what_moved([Mover("AAPL", d("340")), Mover("MSFT", None)])

    assert result == "AAPL is your only position that's moved, up $340.00."


def test_a_dominant_gain_says_it_is_almost_everything() -> None:
    result = what_moved([Mover("AAPL", d("3900")), Mover("MSFT", d("100"))])

    assert result is not None
    assert result.startswith("Almost all of your gain sits in one stock: AAPL, up $3,900.00.")


def test_a_dominant_loss_says_it_is_almost_everything() -> None:
    result = what_moved([Mover("NVDA", d("-3900")), Mover("MSFT", d("-100"))])

    assert result == "Almost all of your loss sits in one stock: NVDA, down $3,900.00."


def test_an_evenly_split_portfolio_just_names_the_biggest() -> None:
    # Three similar gains: no single stock is the story, so don't pretend one is.
    result = what_moved([Mover("AAPL", d("400")), Mover("MSFT", d("350")), Mover("KO", d("300"))])

    assert result == "Your biggest gain right now is AAPL, up $400.00."


def test_the_dominance_threshold_is_inclusive() -> None:
    # 600 of 1,000 total movement is exactly 60%.
    at = what_moved([Mover("AAPL", d("600")), Mover("MSFT", d("400"))])
    below = what_moved([Mover("AAPL", d("599")), Mover("MSFT", d("401"))])

    assert at is not None and at.startswith("Almost all of your gain")
    assert below is not None and below.startswith("Your biggest gain")


def test_a_winner_and_a_loser_both_get_named() -> None:
    result = what_moved([Mover("AAPL", d("500")), Mover("NVDA", d("-450"))])

    # Neither dominates, and the picture isn't whole without both sides.
    assert result == (
        "Your biggest gain right now is AAPL, up $500.00. "
        "NVDA is going the other way, down $450.00."
    )


def test_a_biggest_drop_is_described_not_judged() -> None:
    result = what_moved([Mover("NVDA", d("-450")), Mover("AAPL", d("400"))])

    assert result is not None
    assert result.startswith("Your biggest drop right now is NVDA, down $450.00.")
    assert "AAPL is going the other way, up $400.00." in result


def test_all_in_one_direction_names_no_other_side() -> None:
    result = what_moved([Mover("AAPL", d("400")), Mover("MSFT", d("350"))])

    assert result is not None
    assert "the other way" not in result


def test_money_reads_with_separators_and_no_bare_minus() -> None:
    result = what_moved([Mover("NVDA", d("-12345.67"))])

    assert result == "NVDA is your only position that's moved, down $12,345.67."
    assert "-" not in result


def test_the_sentence_never_tells_you_what_to_do() -> None:
    """Hard rule #2. The sentence names what moved; it never suggests acting on it."""
    banned = ("you should", "consider", "sell", "buy", "trim", "cut your", "add to")
    cases = [
        [Mover("AAPL", d("3900")), Mover("MSFT", d("100"))],
        [Mover("NVDA", d("-3900")), Mover("MSFT", d("-100"))],
        [Mover("AAPL", d("500")), Mover("NVDA", d("-450"))],
        [Mover("AAPL", d("340"))],
    ]
    for movers in cases:
        result = what_moved(movers)
        assert result is not None
        for phrase in banned:
            assert phrase not in result.lower(), f"drifted into advice: {phrase!r}"


def test_the_sentence_never_claims_to_explain_the_total() -> None:
    """These are unrealized figures on what's held now.

    Anyone who has sold a winner has gains this sentence cannot see, so no phrasing may
    imply it accounts for the account's whole gain.
    """
    banned = ("since you started", "that's where", "all of that came from", "your total")
    result = what_moved([Mover("AAPL", d("3900")), Mover("MSFT", d("100"))])

    assert result is not None
    for phrase in banned:
        assert phrase not in result.lower()
