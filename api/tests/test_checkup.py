"""Unit tests for the portfolio check-up.

Pure functions over made-up facts, so every threshold is checked exactly, with no network
and no database anywhere near it. The copy matters as much as the arithmetic here, so a few
of these assert on the wording: a check must never tell someone what to do (hard rule #2).
"""

from __future__ import annotations

from decimal import Decimal

from services.analysis.checkup import (
    Finding,
    PortfolioFacts,
    evaluate,
)


def d(value: str) -> Decimal:
    return Decimal(value)


def facts(**overrides: object) -> PortfolioFacts:
    """A middle-of-the-road portfolio: five names, evenly spread, mostly invested."""
    base: dict[str, object] = {
        "position_count": 5,
        "top_symbol": "AAPL",
        "top_weight": d("25"),
        "effective_holdings": d("4.5"),
        "cash_weight": d("10"),
        "top_sector": "Technology",
        "top_sector_weight": d("30"),
    }
    base.update(overrides)
    return PortfolioFacts(**base)  # type: ignore[arg-type]  # kwargs built above are typed


def by_key(findings: list[Finding]) -> dict[str, Finding]:
    return {finding.key: finding for finding in findings}


def test_an_empty_portfolio_has_nothing_to_say() -> None:
    # Nothing is held, so there is no honest observation to make. Say nothing.
    assert evaluate(facts(position_count=0, top_symbol=None)) == []


def test_a_healthy_portfolio_passes_every_check() -> None:
    found = by_key(evaluate(facts()))

    assert {finding.status for finding in found.values()} == {"ok"}
    # Every check still carries its lesson, because the teaching is the point, not the verdict.
    assert all(finding.lesson for finding in found.values())


def test_one_dominant_position_is_notable() -> None:
    found = by_key(evaluate(facts(top_weight=d("62"))))

    assert found["one_big_position"].status == "notable"
    assert "AAPL is 62% of what you own" in found["one_big_position"].detail


def test_the_big_position_threshold_is_inclusive() -> None:
    assert by_key(evaluate(facts(top_weight=d("40"))))["one_big_position"].status == "notable"
    assert by_key(evaluate(facts(top_weight=d("39.9"))))["one_big_position"].status == "ok"


def test_weights_are_read_as_whole_percents() -> None:
    # A sentence reading "61.73%" is noise, so the copy rounds. 61.5 rounds up.
    found = by_key(evaluate(facts(top_weight=d("61.5"))))

    assert "62%" in found["one_big_position"].detail


def test_owning_one_or_two_companies_is_notable() -> None:
    assert by_key(evaluate(facts(position_count=1)))["how_many_companies"].status == "notable"
    assert by_key(evaluate(facts(position_count=2)))["how_many_companies"].status == "notable"
    assert by_key(evaluate(facts(position_count=3)))["how_many_companies"].status == "ok"


def test_one_company_reads_as_singular() -> None:
    found = by_key(evaluate(facts(position_count=1)))

    assert found["how_many_companies"].detail == "You own 1 company."


def test_a_long_list_that_moves_like_one_bet_is_notable() -> None:
    found = by_key(evaluate(facts(position_count=10, effective_holdings=d("1.4"))))

    assert found["spread_of_bets"].status == "notable"
    assert "10 companies" in found["spread_of_bets"].detail
    assert "1.4 equally sized bets" in found["spread_of_bets"].detail


def test_the_spread_check_is_skipped_when_it_would_just_repeat_itself() -> None:
    # With one or two names, "it behaves like 1.2 bets" says nothing the biggest-position
    # check hasn't already said, so it is left out rather than shown.
    assert "spread_of_bets" not in by_key(evaluate(facts(position_count=2)))
    assert "spread_of_bets" in by_key(evaluate(facts(position_count=3)))


def test_a_crowded_sector_is_notable() -> None:
    found = by_key(evaluate(facts(top_sector="Semiconductors", top_sector_weight=d("78"))))

    assert found["sector_spread"].status == "notable"
    assert "78% of what you own is in one industry, Semiconductors" in found["sector_spread"].detail


def test_unknown_sectors_say_so_rather_than_guess() -> None:
    found = by_key(evaluate(facts(top_sector=None, top_sector_weight=Decimal(0))))

    assert found["sector_spread"].status == "unknown"
    assert "couldn't look up" in found["sector_spread"].detail
    # The lesson is still there: not knowing the split doesn't make the idea less worth
    # explaining.
    assert found["sector_spread"].lesson


def test_the_sector_check_is_skipped_for_a_single_holding() -> None:
    # One company is trivially 100% of one industry, which teaches nothing.
    assert "sector_spread" not in by_key(evaluate(facts(position_count=1)))


def test_a_big_cash_pile_is_notable() -> None:
    found = by_key(evaluate(facts(cash_weight=d("73"))))

    assert found["cash_on_the_sidelines"].status == "notable"
    assert "73% of your money is still sitting in cash" in found["cash_on_the_sidelines"].detail


def test_cash_is_always_reported_even_when_small() -> None:
    found = by_key(evaluate(facts(cash_weight=d("4"))))

    assert found["cash_on_the_sidelines"].status == "ok"
    assert "4%" in found["cash_on_the_sidelines"].detail


def test_no_check_ever_tells_you_what_to_do() -> None:
    """Hard rule #2, asserted rather than trusted.

    Every check runs on a portfolio that trips all of them at once, and none of the copy is
    allowed to reach for the imperative. This is the wording guard for the whole feature.
    """
    tripped = evaluate(
        facts(
            position_count=1,
            top_weight=d("100"),
            effective_holdings=d("1"),
            top_sector="Technology",
            top_sector_weight=d("100"),
            cash_weight=d("80"),
        )
    )
    banned = (
        "you should",
        "we recommend",
        "consider buying",
        "consider selling",
        "sell some",
        "buy more",
        "diversify now",
        "reduce your",
    )
    for finding in tripped:
        words = f"{finding.title} {finding.detail} {finding.lesson}".lower()
        for phrase in banned:
            assert phrase not in words, f"{finding.key} drifted into advice: {phrase!r}"


def test_findings_come_back_in_a_stable_order() -> None:
    keys = [finding.key for finding in evaluate(facts())]

    assert keys == [
        "one_big_position",
        "how_many_companies",
        "spread_of_bets",
        "sector_spread",
        "cash_on_the_sidelines",
    ]
