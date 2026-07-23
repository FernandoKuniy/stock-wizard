"""Unit tests for the portfolio history and benchmark math.

Pure functions over made-up prices, so the arithmetic is checked exactly, with no
network and no database anywhere near it.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from services.analysis.history import (
    Trade,
    ValuePoint,
    benchmark_series,
    compare_to_benchmark,
    portfolio_value_series,
    trim_to,
)

START = Decimal("100000")

# Five consecutive trading days.
DAYS = [date(2026, 3, 2), date(2026, 3, 3), date(2026, 3, 4), date(2026, 3, 5), date(2026, 3, 6)]


def d(value: str) -> Decimal:
    return Decimal(value)


def closes(prices: dict[date, str]) -> dict[date, Decimal]:
    return {day: Decimal(price) for day, price in prices.items()}


def values(points: list[ValuePoint]) -> list[Decimal]:
    return [point.value for point in points]


def test_all_cash_is_a_flat_line() -> None:
    series = portfolio_value_series(START, [], {}, DAYS)

    assert values(series) == [START] * 5
    assert [point.on for point in series] == DAYS


def test_a_buy_swaps_cash_for_shares_at_that_days_price() -> None:
    # Buy 10 shares at $100 on day 2. Cash drops by $1,000; the shares track the price.
    trades = [Trade("AAPL", "buy", d("10"), d("100"), DAYS[1])]
    prices = {
        "AAPL": closes(
            {DAYS[0]: "90", DAYS[1]: "100", DAYS[2]: "110", DAYS[3]: "120", DAYS[4]: "130"}
        )
    }

    series = portfolio_value_series(START, trades, prices, DAYS)

    assert values(series) == [
        d("100000"),  # day 1: not bought yet, all cash
        d("100000"),  # day 2: 99,000 cash + 10 * 100. Buying does not change your worth.
        d("100100"),  # day 3: 99,000 + 10 * 110
        d("100200"),
        d("100300"),
    ]


def test_selling_locks_the_gain_into_cash() -> None:
    trades = [
        Trade("AAPL", "buy", d("10"), d("100"), DAYS[1]),
        Trade("AAPL", "sell", d("10"), d("120"), DAYS[3]),
    ]
    prices = {
        "AAPL": closes(
            {DAYS[0]: "90", DAYS[1]: "100", DAYS[2]: "110", DAYS[3]: "120", DAYS[4]: "50"}
        )
    }

    series = portfolio_value_series(START, trades, prices, DAYS)

    # Sold on day 4 for 1,200 after paying 1,000, so 100,200 in cash.
    assert values(series)[3] == d("100200")
    # Day 5: the price collapses, but we are out. The gain stays banked.
    assert values(series)[4] == d("100200")


def test_a_partial_sell_keeps_the_rest_priced() -> None:
    trades = [
        Trade("AAPL", "buy", d("10"), d("100"), DAYS[0]),
        Trade("AAPL", "sell", d("4"), d("110"), DAYS[2]),
    ]
    prices = {
        "AAPL": closes(
            {DAYS[0]: "100", DAYS[1]: "110", DAYS[2]: "110", DAYS[3]: "120", DAYS[4]: "120"}
        )
    }

    series = portfolio_value_series(START, trades, prices, DAYS)

    # Cash: 100,000 - 1,000 + 440 = 99,440. Held: 6 shares.
    assert values(series)[2] == d("99440") + d("6") * d("110")
    assert values(series)[3] == d("99440") + d("6") * d("120")


def test_a_missing_bar_carries_the_last_close_forward() -> None:
    # No bar on day 3 (a holiday, say). The position is carried at day 2's close.
    trades = [Trade("AAPL", "buy", d("10"), d("100"), DAYS[0])]
    prices = {"AAPL": closes({DAYS[0]: "100", DAYS[1]: "110", DAYS[3]: "130", DAYS[4]: "140"})}

    series = portfolio_value_series(START, trades, prices, DAYS)

    assert values(series)[1] == d("99000") + d("10") * d("110")
    assert values(series)[2] == d("99000") + d("10") * d("110")  # carried, not dropped
    assert values(series)[3] == d("99000") + d("10") * d("130")


def test_a_symbol_with_no_price_yet_is_not_counted() -> None:
    # The symbol only starts trading on day 4, and we only buy it once it does.
    trades = [Trade("NEW", "buy", d("10"), d("50"), DAYS[3])]
    prices = {"NEW": closes({DAYS[3]: "50", DAYS[4]: "60"})}

    series = portfolio_value_series(START, trades, prices, DAYS)

    assert values(series)[0] == START  # nothing held, nothing invented
    assert values(series)[3] == d("99500") + d("10") * d("50")
    assert values(series)[4] == d("99500") + d("10") * d("60")


def test_several_holdings_add_up() -> None:
    trades = [
        Trade("AAPL", "buy", d("10"), d("100"), DAYS[0]),
        Trade("MSFT", "buy", d("5"), d("200"), DAYS[0]),
    ]
    prices = {
        "AAPL": closes({DAYS[0]: "100", DAYS[1]: "110"}),
        "MSFT": closes({DAYS[0]: "200", DAYS[1]: "210"}),
    }

    series = portfolio_value_series(START, trades, prices, DAYS)

    # Cash: 100,000 - 1,000 - 1,000 = 98,000
    assert values(series)[0] == d("98000") + d("10") * d("100") + d("5") * d("200")
    assert values(series)[1] == d("98000") + d("10") * d("110") + d("5") * d("210")


def test_fractional_shares_stay_exact() -> None:
    trades = [Trade("AAPL", "buy", d("2.5"), d("199.99"), DAYS[0])]
    prices = {"AAPL": closes({DAYS[0]: "199.99", DAYS[1]: "205.50"})}

    series = portfolio_value_series(START, trades, prices, DAYS)

    cost = d("2.5") * d("199.99")  # 499.975 -> the sim rounds cash to 4dp
    assert values(series)[0] == START - cost + d("2.5") * d("199.99")
    assert values(series)[1] == START - cost + d("2.5") * d("205.50")


def test_benchmark_buys_the_index_on_day_one_and_holds() -> None:
    spy = closes({DAYS[0]: "500", DAYS[1]: "505", DAYS[2]: "510", DAYS[3]: "490", DAYS[4]: "550"})

    series = benchmark_series(START, spy, DAYS)

    shares = START / d("500")  # 200 shares
    assert values(series) == [shares * d(p) for p in ["500", "505", "510", "490", "550"]]
    assert values(series)[0] == START  # always starts at the starting balance


def test_benchmark_is_empty_without_an_opening_price() -> None:
    # The index has no bar until day 3, so there is no honest place to start the line.
    spy = closes({DAYS[2]: "510"})

    assert benchmark_series(START, spy, DAYS) == []
    assert benchmark_series(START, spy, []) == []


def test_comparison_says_who_is_ahead() -> None:
    portfolio = portfolio_value_series(
        START,
        [Trade("AAPL", "buy", d("100"), d("100"), DAYS[0])],
        {"AAPL": closes({DAYS[0]: "100", DAYS[4]: "150"})},
        DAYS,
    )
    spy = closes({DAYS[0]: "500", DAYS[4]: "550"})
    benchmark = benchmark_series(START, spy, DAYS)

    result = compare_to_benchmark(START, portfolio, benchmark)
    assert result is not None

    # Portfolio: 90,000 cash + 100 shares at 150 = 105,000, so up 5%.
    assert result.portfolio_value == d("105000")
    assert result.portfolio_percent == d("5")
    # Index: 200 shares from 500 to 550 = 110,000, so up 10%.
    assert result.benchmark_value == d("110000")
    assert result.benchmark_percent == d("10")
    # The index won by $5,000.
    assert result.difference == d("-5000")


def test_comparison_needs_both_lines() -> None:
    points = portfolio_value_series(START, [], {}, DAYS)

    assert compare_to_benchmark(START, points, []) is None
    assert compare_to_benchmark(START, [], points) is None
    assert compare_to_benchmark(Decimal(0), points, points) is None


def test_trim_keeps_everything_without_a_start() -> None:
    points = portfolio_value_series(START, [], {}, DAYS)

    assert trim_to(points, None) == points


def test_trim_drops_the_days_before_the_window() -> None:
    points = portfolio_value_series(START, [], {}, DAYS)

    trimmed = trim_to(points, DAYS[2])

    assert [point.on for point in trimmed] == DAYS[2:]


def test_trim_includes_the_first_day_of_the_window() -> None:
    points = portfolio_value_series(START, [], {}, DAYS)

    # On or after, not strictly after: the day the window opens is part of it.
    assert trim_to(points, DAYS[0])[0].on == DAYS[0]


def test_trim_to_a_start_before_the_account_keeps_the_whole_life() -> None:
    points = portfolio_value_series(START, [], {}, DAYS)

    # Asking for a year on a five-day-old account is that account's whole life.
    assert trim_to(points, date(2020, 1, 1)) == points


def test_trim_past_the_end_leaves_nothing() -> None:
    points = portfolio_value_series(START, [], {}, DAYS)

    assert trim_to(points, date(2030, 1, 1)) == []


def test_a_shorter_window_is_measured_from_where_it_opened() -> None:
    """The point of the period selector: this month's answer, not since-you-started.

    A stock that doubled in the first half and sat still in the second should read as a big
    gain over the whole stretch and as flat over the second half.
    """
    trades = [Trade("AAPL", "buy", d("1000"), d("100"), DAYS[0])]
    aapl = closes({DAYS[0]: "100", DAYS[1]: "150", DAYS[2]: "200", DAYS[3]: "200", DAYS[4]: "200"})
    full = portfolio_value_series(START, trades, {"AAPL": aapl}, DAYS)

    # Whole life: 1,000 shares bought at 100, now worth 200. Cash is unchanged at 0 left over.
    assert full[0].value == START  # 0 cash + 1,000 shares at 100
    assert full[-1].value == d("200000")

    window = trim_to(full, DAYS[2])
    baseline = window[0].value
    spy = closes({DAYS[2]: "400", DAYS[3]: "400", DAYS[4]: "440"})
    benchmark = benchmark_series(baseline, spy, [point.on for point in window])

    result = compare_to_benchmark(baseline, window, benchmark)
    assert result is not None

    # Flat over the window, even though it doubled over the account's whole life.
    assert result.portfolio_value == d("200000")
    assert result.portfolio_percent == d("0")
    # Both lines start at the same number, which is what keeps the comparison honest.
    assert benchmark[0].value == baseline
    # The index rose 10% over the same stretch, so sitting still cost $20,000 of ground.
    assert result.benchmark_percent == d("10")
    assert result.difference == d("-20000")
