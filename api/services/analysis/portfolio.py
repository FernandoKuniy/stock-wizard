"""Deterministic portfolio math: the "numbers" layer.

Every financial figure the app or the AI tutor shows is computed here, in plain
Python, never by the LLM (see the two hard rules in CLAUDE.md). Each function
takes plain data in and returns exact ``Decimal`` values out, with names the rest
of the app and the tutor can reference directly. No rounding happens here: the
API boundary rounds for display so precision is never lost mid-calculation.

Callers must supply a current price for every position's symbol in ``prices``.
Handling a missing or failed quote is the caller's job, not this layer's.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal

_ZERO = Decimal(0)
_HUNDRED = Decimal(100)


@dataclass(frozen=True)
class Position:
    """One holding as the analysis layer sees it."""

    symbol: str
    quantity: Decimal
    avg_cost: Decimal


@dataclass(frozen=True)
class GainLoss:
    """A profit/loss figure, both absolute (money) and percent."""

    absolute: Decimal
    percent: Decimal


def position_market_value(quantity: Decimal, price: Decimal) -> Decimal:
    """What the shares are worth right now."""
    return quantity * price


def position_cost_basis(quantity: Decimal, avg_cost: Decimal) -> Decimal:
    """What the shares cost, on average, to acquire."""
    return quantity * avg_cost


def position_gain_loss(quantity: Decimal, avg_cost: Decimal, price: Decimal) -> GainLoss:
    """Unrealized profit/loss on one holding, absolute and percent."""
    cost = position_cost_basis(quantity, avg_cost)
    value = position_market_value(quantity, price)
    absolute = value - cost
    percent = (absolute / cost * _HUNDRED) if cost != _ZERO else _ZERO
    return GainLoss(absolute=absolute, percent=percent)


def holdings_market_value(positions: Iterable[Position], prices: Mapping[str, Decimal]) -> Decimal:
    """Total market value of the holdings alone (cash not included)."""
    total = _ZERO
    for position in positions:
        total += position_market_value(position.quantity, prices[position.symbol])
    return total


def portfolio_total_value(
    cash: Decimal, positions: Iterable[Position], prices: Mapping[str, Decimal]
) -> Decimal:
    """Everything the account is worth: cash plus the holdings' market value."""
    return cash + holdings_market_value(positions, prices)


def total_gain_loss(
    cash: Decimal,
    starting_balance: Decimal,
    positions: Iterable[Position],
    prices: Mapping[str, Decimal],
) -> GainLoss:
    """Account performance: current total value against the starting balance.

    This captures both realized gains (already back in cash) and unrealized gains
    (still in holdings), which is the honest "how am I doing?" number.
    """
    value = portfolio_total_value(cash, positions, prices)
    absolute = value - starting_balance
    percent = (absolute / starting_balance * _HUNDRED) if starting_balance != _ZERO else _ZERO
    return GainLoss(absolute=absolute, percent=percent)


def position_weights(
    cash: Decimal, positions: Iterable[Position], prices: Mapping[str, Decimal]
) -> dict[str, Decimal]:
    """Each holding's share of the whole portfolio, as a percent.

    Weights are measured against the total value with cash included, so the
    holding weights plus the cash weight sum to 100. Returns an empty mapping when
    the portfolio is worth nothing.
    """
    positions = list(positions)
    total = portfolio_total_value(cash, positions, prices)
    if total == _ZERO:
        return {}
    return {
        position.symbol: (
            position_market_value(position.quantity, prices[position.symbol]) / total * _HUNDRED
        )
        for position in positions
    }
