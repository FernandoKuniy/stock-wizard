"""Unit tests for the portfolio analysis operators (the "numbers" layer).

These figures are literally people's balances, so the layer is tested hard:
gains, losses, zero guards, realized vs unrealized, and weights.
"""

from __future__ import annotations

from decimal import Decimal

from services.analysis.portfolio import (
    GainLoss,
    Position,
    holdings_market_value,
    portfolio_total_value,
    position_cost_basis,
    position_gain_loss,
    position_market_value,
    position_weights,
    total_gain_loss,
)


def test_market_value_and_cost_basis() -> None:
    assert position_market_value(Decimal(10), Decimal(120)) == Decimal(1200)
    assert position_cost_basis(Decimal(10), Decimal(100)) == Decimal(1000)


def test_position_gain() -> None:
    gl = position_gain_loss(Decimal(10), Decimal(100), Decimal(120))
    assert gl == GainLoss(absolute=Decimal(200), percent=Decimal(20))


def test_position_loss() -> None:
    gl = position_gain_loss(Decimal(10), Decimal(100), Decimal(80))
    assert gl.absolute == Decimal(-200)
    assert gl.percent == Decimal(-20)


def test_position_gain_loss_guards_zero_cost() -> None:
    # A zero cost basis (e.g. avg_cost 0) must not divide by zero.
    gl = position_gain_loss(Decimal(10), Decimal(0), Decimal(5))
    assert gl.absolute == Decimal(50)
    assert gl.percent == Decimal(0)


def test_holdings_and_total_value() -> None:
    positions = [
        Position("AAPL", Decimal(10), Decimal(90)),
        Position("MSFT", Decimal(4), Decimal(200)),
    ]
    prices = {"AAPL": Decimal(100), "MSFT": Decimal(250)}
    assert holdings_market_value(positions, prices) == Decimal(2000)
    assert portfolio_total_value(Decimal(8000), positions, prices) == Decimal(10000)


def test_total_gain_loss_counts_realized_and_unrealized() -> None:
    positions = [Position("AAPL", Decimal(10), Decimal(1000))]
    prices = {"AAPL": Decimal(1100)}
    # cash 90k + holdings 11k = 101k against a 100k start -> +1000 (1%).
    gl = total_gain_loss(Decimal(90000), Decimal(100000), positions, prices)
    assert gl.absolute == Decimal(1000)
    assert gl.percent == Decimal(1)


def test_total_gain_loss_all_cash_after_selling() -> None:
    # Sold everything for a small profit: no holdings, cash above the start.
    gl = total_gain_loss(Decimal("100500"), Decimal(100000), [], {})
    assert gl.absolute == Decimal(500)
    assert gl.percent == Decimal("0.5")


def test_total_gain_loss_guards_zero_start() -> None:
    gl = total_gain_loss(Decimal(0), Decimal(0), [], {})
    assert gl.percent == Decimal(0)


def test_position_weights_sum_with_cash_to_100() -> None:
    positions = [
        Position("AAPL", Decimal(10), Decimal(50)),
        Position("MSFT", Decimal(4), Decimal(100)),
    ]
    prices = {"AAPL": Decimal(100), "MSFT": Decimal(250)}  # 1000 + 1000 = 2000
    weights = position_weights(Decimal(8000), positions, prices)  # total 10000

    assert weights["AAPL"] == Decimal(10)
    assert weights["MSFT"] == Decimal(10)
    cash_weight = Decimal(8000) / Decimal(10000) * Decimal(100)
    assert weights["AAPL"] + weights["MSFT"] + cash_weight == Decimal(100)


def test_position_weights_empty_when_worthless() -> None:
    assert position_weights(Decimal(0), [], {}) == {}
