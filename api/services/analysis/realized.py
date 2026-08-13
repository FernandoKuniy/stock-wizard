"""Realized profit and loss: what you've locked in by selling, worked out from the ledger.

Still the "numbers" layer: pure deterministic Python, no LLM near it. Beginners conflate a gain
"on paper" (still riding on what they hold) with money they've actually made. This splits the
first out: it replays an account's buys and sells in order, tracking a weighted average cost the
same way the sim's engine does, and books a realized gain every time shares are sold, proceeds
minus the average cost of the shares that left. That's money already back in cash.

Realized here, plus the unrealized gain on what's still held, plus any dividends received, add up
to the account's total gain since it opened. No rounding happens here; the API boundary rounds.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Protocol

_ZERO = Decimal(0)


class Fill(Protocol):
    """The slice of a transaction this needs: a buy or sell of some shares at a price.

    Read-only members, so anything with these fields satisfies it: a Transaction row, a frozen
    dataclass, a plain one. This layer never writes them, so the contract shouldn't demand it.
    """

    @property
    def symbol(self) -> str: ...
    @property
    def side(self) -> str: ...
    @property
    def quantity(self) -> Decimal: ...
    @property
    def price(self) -> Decimal: ...


def realized_pnl(fills: Iterable[Fill]) -> Decimal:
    """Total realized profit/loss over the fills, in dollars, using the average-cost method.

    ``fills`` must be in the order they happened. A buy re-averages the cost of what's held; a
    sell books ``shares * (price - average_cost)`` and leaves the average untouched, so selling
    after several buys locks the gain in against the blended price actually paid. Selling a
    position down to nothing and buying back in starts the average fresh, which is exactly how
    the live holding's ``avg_cost`` behaves.
    """
    quantity: dict[str, Decimal] = {}
    avg_cost: dict[str, Decimal] = {}
    realized = _ZERO

    for fill in fills:
        held = quantity.get(fill.symbol, _ZERO)
        if fill.side == "buy":
            new_quantity = held + fill.quantity
            if new_quantity > _ZERO:
                basis = held * avg_cost.get(fill.symbol, _ZERO) + fill.quantity * fill.price
                avg_cost[fill.symbol] = basis / new_quantity
            quantity[fill.symbol] = new_quantity
        else:  # sell
            realized += fill.quantity * (fill.price - avg_cost.get(fill.symbol, _ZERO))
            quantity[fill.symbol] = held - fill.quantity

    return realized
