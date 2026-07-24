"""Unit tests for the time machine: what one lump sum would have done.

Pure functions over a map of closing prices, so these are plain arithmetic with no database
and no market client. The cases that matter are the honest ones: a stock that lost, a start
date on a closed market, a symbol that wasn't trading yet, and a missing index.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from services.analysis.whatif import NotEnoughHistory, spread_over, what_if

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


# Twelve monthly closes 30 days apart, so a one-year window splits into twelve instalments.
DRIP_START = date(2025, 1, 6)
DRIP_DAYS = [DRIP_START + timedelta(days=30 * i) for i in range(12)]


def flat(price: str) -> dict[date, Decimal]:
    """Every instalment day at the same price, plus a final close to value it at."""
    closes = {day: Decimal(price) for day in DRIP_DAYS}
    closes[DRIP_START + timedelta(days=365)] = Decimal(price)
    return closes


def test_a_window_too_short_to_split_has_no_spread() -> None:
    # A month is one instalment, which is just the lump sum under another name.
    assert spread_over(Decimal("1200"), "AAPL", STOCK, start=DRIP_START, window_days=30) is None
    assert what_if(Decimal("1000"), "AAPL", STOCK, start=date(2025, 1, 6)).spread is None


def test_a_year_splits_into_twelve_instalments() -> None:
    leg = spread_over(Decimal("1200"), "AAPL", flat("100"), start=DRIP_START, window_days=365)
    assert leg is not None

    assert leg.instalments == 12
    assert leg.each == Decimal("100")
    assert leg.first_on == DRIP_DAYS[0]
    assert leg.last_on == DRIP_DAYS[11]


def test_six_months_splits_into_six() -> None:
    leg = spread_over(Decimal("600"), "AAPL", flat("100"), start=DRIP_START, window_days=182)
    assert leg is not None

    assert leg.instalments == 6


def test_at_a_flat_price_spreading_matches_the_lump_sum() -> None:
    closes = flat("100")
    leg = spread_over(Decimal("1200"), "AAPL", closes, start=DRIP_START, window_days=365)
    assert leg is not None

    # Nothing moved, so when you bought made no difference. 12 shares either way.
    assert leg.shares == Decimal("12")
    assert leg.value_now == Decimal("1200")
    assert leg.gain_loss == Decimal("0")


def test_spreading_wins_when_the_price_falls_first() -> None:
    # Halves for the back half of the year, then recovers to where it started.
    closes = {day: Decimal("100") for day in DRIP_DAYS[:6]}
    closes.update({day: Decimal("50") for day in DRIP_DAYS[6:]})
    closes[DRIP_START + timedelta(days=365)] = Decimal("100")

    lump = what_if(Decimal("1200"), "AAPL", closes, start=DRIP_START, window_days=365)
    assert lump.spread is not None

    # Lump sum: 12 shares at 100, back to 100, so flat. Spreading picked up cheap shares.
    assert lump.stock.value_now == Decimal("1200")
    assert lump.spread.value_now > lump.stock.value_now


def test_the_lump_sum_wins_when_the_price_only_rises() -> None:
    # Doubles halfway through and stays there.
    closes = {day: Decimal("100") for day in DRIP_DAYS[:6]}
    closes.update({day: Decimal("200") for day in DRIP_DAYS[6:]})
    closes[DRIP_START + timedelta(days=365)] = Decimal("200")

    result = what_if(Decimal("1200"), "AAPL", closes, start=DRIP_START, window_days=365)
    assert result.spread is not None

    # Buying it all early beat drip-feeding into a rising price. This is why the feature is
    # a comparison and not a technique we recommend.
    assert result.stock.value_now == Decimal("2400")
    assert result.spread.value_now < result.stock.value_now


def test_the_instalments_add_up_to_exactly_the_amount() -> None:
    # 1,000 over 12 doesn't divide evenly, so the last instalment carries the remainder.
    closes = flat("100")
    leg = spread_over(Decimal("1000"), "AAPL", closes, start=DRIP_START, window_days=365)
    assert leg is not None

    # At a flat $100 the shares are the total spent divided by 100, so exactness shows up here.
    assert leg.shares == Decimal("10")
    assert leg.value_now == Decimal("1000")
    assert leg.gain_loss == Decimal("0")


def test_an_instalment_we_cannot_price_drops_the_whole_comparison() -> None:
    # History stops halfway through, so the later instalments have nothing to buy at. A
    # partial answer over fewer instalments than the label claims would be misleading.
    closes = {day: Decimal("100") for day in DRIP_DAYS[:6]}

    assert spread_over(Decimal("1200"), "AAPL", closes, start=DRIP_START, window_days=365) is None
