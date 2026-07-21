"""Unit tests for the time machine: what one lump sum would have done.

Pure functions over a map of closing prices, so these are plain arithmetic with no database
and no market client. The cases that matter are the honest ones: a stock that lost, a start
date on a closed market, a symbol that wasn't trading yet, and a missing index.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from services.analysis.whatif import NotEnoughHistory, what_if

# A stock that doubles, and an index that only goes up 25% over the same window.
STOCK = {
    date(2025, 1, 6): Decimal("100"),
    date(2025, 6, 2): Decimal("150"),
    date(2026, 1, 5): Decimal("200"),
}
INDEX = {
    date(2025, 1, 6): Decimal("400"),
    date(2025, 6, 2): Decimal("450"),
    date(2026, 1, 5): Decimal("500"),
}


def test_a_lump_sum_that_doubled() -> None:
    result = what_if(Decimal("1000"), "AAPL", STOCK, start=date(2025, 1, 6))

    leg = result.stock
    assert leg.shares == Decimal("10")  # $1,000 at $100
    assert leg.buy_price == Decimal("100")
    assert leg.latest_price == Decimal("200")
    assert leg.value_now == Decimal("2000")
    assert leg.gain_loss == Decimal("1000")
    assert leg.gain_loss_percent == Decimal("100")


def test_a_lump_sum_that_lost_money() -> None:
    falling = {date(2025, 1, 6): Decimal("200"), date(2026, 1, 5): Decimal("50")}

    leg = what_if(Decimal("1000"), "AAPL", falling, start=date(2025, 1, 6)).stock

    # Picking a bad moment is the honest half of the lesson, so it reads as a real loss.
    assert leg.value_now == Decimal("250")
    assert leg.gain_loss == Decimal("-750")
    assert leg.gain_loss_percent == Decimal("-75")


def test_a_start_date_the_market_was_shut_rolls_forward() -> None:
    # A Sunday, a holiday, whatever: buy at the next day the market actually opened.
    leg = what_if(Decimal("1000"), "AAPL", STOCK, start=date(2025, 1, 4)).stock

    assert leg.bought_on == date(2025, 1, 6)
    assert leg.buy_price == Decimal("100")


def test_a_mid_window_start_uses_that_days_close() -> None:
    leg = what_if(Decimal("900"), "AAPL", STOCK, start=date(2025, 6, 2)).stock

    assert leg.bought_on == date(2025, 6, 2)
    assert leg.shares == Decimal("6")  # $900 at $150
    assert leg.value_now == Decimal("1200")


def test_shares_stay_exact_fractions() -> None:
    # A hypothetical isn't a fill, so we don't round the share count down to 6dp the way a
    # real order has to. Rounding it would shave a sliver off and show a loss the user never
    # took on a price that never moved.
    awkward = {date(2025, 1, 6): Decimal("3")}

    leg = what_if(Decimal("1000"), "AAPL", awkward, start=date(2025, 1, 6)).stock

    assert leg.shares == Decimal("1000") / Decimal("3")
    # Same day in and out, so to the cent the money is exactly what went in.
    assert leg.value_now.quantize(Decimal("0.01")) == Decimal("1000.00")
    assert leg.gain_loss.quantize(Decimal("0.01")) == Decimal("0.00")


def test_the_index_comparison_shows_the_stock_winning() -> None:
    result = what_if(
        Decimal("1000"),
        "AAPL",
        STOCK,
        start=date(2025, 1, 6),
        benchmark_symbol="SPY",
        benchmark_closes=INDEX,
    )

    assert result.benchmark is not None
    assert result.benchmark.value_now == Decimal("1250")  # 2.5 shares at $500
    # The stock doubled while the index added 25%, so the stock is $750 ahead.
    assert result.difference == Decimal("750")


def test_the_index_comparison_shows_the_stock_losing() -> None:
    # The lesson that matters most: one company trailing the whole market.
    laggard = {date(2025, 1, 6): Decimal("100"), date(2026, 1, 5): Decimal("110")}

    result = what_if(
        Decimal("1000"),
        "AAPL",
        laggard,
        start=date(2025, 1, 6),
        benchmark_symbol="SPY",
        benchmark_closes=INDEX,
    )

    assert result.stock.value_now == Decimal("1100")
    assert result.benchmark is not None
    assert result.benchmark.value_now == Decimal("1250")
    assert result.difference == Decimal("-150")


def test_a_missing_index_still_answers_the_question() -> None:
    result = what_if(
        Decimal("1000"),
        "AAPL",
        STOCK,
        start=date(2025, 1, 6),
        benchmark_symbol="SPY",
        benchmark_closes={},
    )

    # Same asymmetry the performance chart uses: no index costs only the comparison.
    assert result.stock.value_now == Decimal("2000")
    assert result.benchmark is None
    assert result.difference is None


def test_an_index_that_doesnt_reach_back_is_left_out() -> None:
    short_index = {date(2026, 1, 5): Decimal("500")}

    result = what_if(
        Decimal("1000"),
        "AAPL",
        STOCK,
        start=date(2025, 1, 6),
        benchmark_symbol="SPY",
        benchmark_closes=short_index,
    )

    # The index does have a close, but a year after the day we'd have bought the stock.
    # Comparing them would measure the calendar, not the choice, so there's no comparison.
    assert result.stock.value_now == Decimal("2000")
    assert result.benchmark is None
    assert result.difference is None


def test_a_symbol_with_no_history_that_far_back_refuses() -> None:
    recent_ipo = {date(2026, 1, 5): Decimal("50")}

    with pytest.raises(NotEnoughHistory):
        what_if(Decimal("1000"), "NEW", recent_ipo, start=date(2026, 2, 1))


def test_no_history_at_all_refuses() -> None:
    with pytest.raises(NotEnoughHistory):
        what_if(Decimal("1000"), "AAPL", {}, start=date(2025, 1, 6))


def test_a_non_positive_amount_is_a_programming_error() -> None:
    with pytest.raises(ValueError):
        what_if(Decimal("0"), "AAPL", STOCK, start=date(2025, 1, 6))
