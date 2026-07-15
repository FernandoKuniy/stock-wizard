"""Unit tests for the concentration and volatility operators.

Same bar as the rest of the analysis layer: these numbers are what the tutor quotes
back to a user about their own money, so the pure functions get exercised hard.
"""

from __future__ import annotations

from decimal import Decimal

from services.analysis.risk import (
    Concentration,
    concentration,
    daily_returns,
    volatility,
)


def test_concentration_single_holding_is_all_in_one() -> None:
    c = concentration({"AAPL": Decimal(1000)})
    assert c == Concentration(
        position_count=1,
        top_symbol="AAPL",
        top_weight=Decimal(100),
        hhi=Decimal(1),
        effective_holdings=Decimal(1),
        sector_weights={},
    )


def test_concentration_two_equal_positions_behaves_like_two() -> None:
    c = concentration({"AAPL": Decimal(1000), "MSFT": Decimal(1000)})
    assert c.position_count == 2
    assert c.top_weight == Decimal(50)
    assert c.hhi == Decimal("0.5")
    assert c.effective_holdings == Decimal(2)


def test_concentration_lopsided_split() -> None:
    c = concentration({"A": Decimal(600), "B": Decimal(300), "C": Decimal(100)})
    assert c.position_count == 3
    assert c.top_symbol == "A"
    assert c.top_weight == Decimal(60)
    # 0.6^2 + 0.3^2 + 0.1^2 = 0.46
    assert c.hhi == Decimal("0.46")
    # Really a bet on about two names, not three.
    assert c.effective_holdings.quantize(Decimal("0.01")) == Decimal("2.17")


def test_concentration_ignores_worthless_positions() -> None:
    c = concentration({"AAPL": Decimal(1000), "OLD": Decimal(0)})
    assert c.position_count == 1
    assert c.top_symbol == "AAPL"


def test_concentration_empty_is_all_zero() -> None:
    c = concentration({})
    assert c == Concentration(
        position_count=0,
        top_symbol=None,
        top_weight=Decimal(0),
        hhi=Decimal(0),
        effective_holdings=Decimal(0),
        sector_weights={},
    )


def test_concentration_sector_breakdown() -> None:
    values = {"AAPL": Decimal(1000), "MSFT": Decimal(1000), "XOM": Decimal(2000)}
    sectors = {"AAPL": "Technology", "MSFT": "Technology", "XOM": "Energy"}
    c = concentration(values, sectors)
    assert c.sector_weights == {"Technology": Decimal(50), "Energy": Decimal(50)}


def test_concentration_unlabelled_sector_is_grouped_as_unknown() -> None:
    # sectors given but this symbol isn't in it: it lands under "Unknown", never dropped.
    c = concentration({"AAPL": Decimal(1000)}, sectors={})
    assert c.sector_weights == {"Unknown": Decimal(100)}


def test_daily_returns_are_exact() -> None:
    assert daily_returns([Decimal(100), Decimal(110), Decimal(99)]) == [
        Decimal("0.1"),
        Decimal("-0.1"),
    ]


def test_daily_returns_skip_a_nonpositive_previous_close() -> None:
    # A zero (or missing-as-zero) prior close has no meaningful return; it's skipped.
    assert daily_returns([Decimal(0), Decimal(100), Decimal(110)]) == [Decimal("0.1")]


def test_volatility_is_stdev_of_returns_as_percent() -> None:
    # Returns +10% then -10%: mean 0, sample variance 0.02, stdev ~14.14%.
    daily = volatility([Decimal(100), Decimal(110), Decimal(99)], annualize=False)
    assert daily is not None
    assert daily.quantize(Decimal("0.0001")) == Decimal("14.1421")


def test_volatility_annualizes_by_root_252() -> None:
    closes = [Decimal(100), Decimal(110), Decimal(99), Decimal(104)]
    daily = volatility(closes, annualize=False)
    annual = volatility(closes)
    assert daily is not None and annual is not None
    assert (annual / daily).quantize(Decimal("0.0001")) == Decimal(252).sqrt().quantize(
        Decimal("0.0001")
    )


def test_volatility_of_a_flat_price_is_zero() -> None:
    assert volatility([Decimal(100), Decimal(100), Decimal(100)]) == Decimal(0)


def test_volatility_needs_at_least_two_returns() -> None:
    assert volatility([Decimal(100)]) is None
    assert volatility([Decimal(100), Decimal(110)]) is None  # only one return
