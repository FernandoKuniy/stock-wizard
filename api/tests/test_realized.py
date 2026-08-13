"""Unit tests for realized profit and loss over the transaction ledger.

Pure math over made-up fills, so the average-cost bookkeeping is checked exactly, with no
network and no database anywhere near it. These are people's banked gains, so the coverage runs
through partial sells, weighted averaging, selling out and buying back in, and several symbols.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from services.analysis.realized import realized_pnl


@dataclass(frozen=True)
class F:
    """A fill, standing in for a Transaction row."""

    symbol: str
    side: str
    quantity: Decimal
    price: Decimal


def buy(symbol: str, quantity: str, price: str) -> F:
    return F(symbol, "buy", Decimal(quantity), Decimal(price))


def sell(symbol: str, quantity: str, price: str) -> F:
    return F(symbol, "sell", Decimal(quantity), Decimal(price))


def test_no_fills_is_zero() -> None:
    assert realized_pnl([]) == Decimal(0)


def test_buying_alone_locks_in_nothing() -> None:
    # Nothing is realized until you sell; it's all still on paper.
    assert realized_pnl([buy("AAPL", "10", "100")]) == Decimal(0)


def test_selling_higher_books_a_gain() -> None:
    fills = [buy("AAPL", "10", "100"), sell("AAPL", "10", "120")]
    assert realized_pnl(fills) == Decimal("200")  # 10 * (120 - 100)


def test_selling_lower_books_a_loss() -> None:
    fills = [buy("AAPL", "10", "100"), sell("AAPL", "10", "80")]
    assert realized_pnl(fills) == Decimal("-200")


def test_a_partial_sell_books_only_the_shares_sold() -> None:
    fills = [buy("AAPL", "10", "100"), sell("AAPL", "4", "150")]
    assert realized_pnl(fills) == Decimal("200")  # 4 * (150 - 100); the other 6 stay on paper


def test_selling_is_measured_against_the_weighted_average_cost() -> None:
    # Two buys average to $150; selling 5 at $180 books 5 * (180 - 150).
    fills = [buy("AAPL", "10", "100"), buy("AAPL", "10", "200"), sell("AAPL", "5", "180")]
    assert realized_pnl(fills) == Decimal("150")


def test_selling_out_then_buying_back_resets_the_average() -> None:
    fills = [
        buy("AAPL", "10", "100"),
        sell("AAPL", "10", "120"),  # +200, position now flat
        buy("AAPL", "5", "200"),  # fresh average of $200
        sell("AAPL", "5", "250"),  # +250 against $200, not the old $100
    ]
    assert realized_pnl(fills) == Decimal("450")


def test_symbols_are_kept_separate() -> None:
    fills = [
        buy("AAPL", "10", "100"),
        buy("MSFT", "10", "300"),
        sell("AAPL", "10", "120"),  # +200
        sell("MSFT", "10", "280"),  # -200
    ]
    assert realized_pnl(fills) == Decimal("0")


def test_fractional_shares_stay_exact() -> None:
    fills = [buy("AAPL", "3", "100"), sell("AAPL", "1.5", "110")]
    assert realized_pnl(fills) == Decimal("15.0")  # 1.5 * (110 - 100)
