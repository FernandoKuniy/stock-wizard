"""Limit orders: resting them, cancelling them, and filling them when the price arrives.

A limit order says "only buy if it drops to $X" (or "only sell if it rises to $X") and then
waits. This app deliberately runs no background job, so an order is checked lazily: whenever
the user loads their portfolio or their orders, ``sweep`` looks at every open order on that
account, fetches a fresh quote, and settles the ones whose price has been reached.

The rules, which the UI states plainly rather than hiding (see docs/decisions.md):

- A fill happens at the **limit price**, not at whatever quote we happened to see. The price
  passed through the limit on its way, so that is where the order would really have
  executed; filling at a later snapshot would pretend the user timed the move.
- **Nothing is set aside** when an order is placed. Cash moves only at fill, so an account
  can rest more buys than it can afford and the first one to cross wins. If the money (or
  the position) is gone by then, the order is cancelled with a reason rather than part-filled.
- Orders are **good until cancelled** and fill **all or nothing**.
- A symbol whose quote we can't get is skipped, never filled. We do not execute on missing
  data, the same instinct that makes the history refuse to draw a line it can't price.

Like the rest of the sim, these functions flush but never commit: the caller owns the
transaction boundary. Settlement itself goes through ``engine.fill_buy`` / ``engine.fill_sell``
so a limit fill is bookkept exactly like a market one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Account, Order
from services.market.client import MarketError
from services.sim.engine import (
    InsufficientShares,
    InvalidOrder,
    QuoteProvider,
    SimError,
    fill_buy,
    fill_sell,
    get_holding,
    shares_str,
)

OPEN = "open"
FILLED = "filled"
CANCELLED = "cancelled"

_SHARES = Decimal("0.000001")  # 6dp, matches orders.quantity
_ZERO = Decimal(0)


class OrderNotFound(SimError):
    """No such order on this account."""


def place(
    session: Session,
    account: Account,
    symbol: str,
    *,
    side: Literal["buy", "sell"],
    limit_price: Decimal,
    quantity: Decimal | None = None,
    amount: Decimal | None = None,
) -> Order:
    """Rest a limit order, sized by share quantity or dollar amount.

    A dollar amount is converted to shares here, in code, at the limit price (hard rule #1):
    at your limit, $500 buys exactly $500 worth. Nothing is debited now.

    A sell is checked against the position up front, because this sim has no shorting and an
    order to sell what you don't own is a mistake worth catching immediately. A buy is *not*
    checked against cash, because with nothing reserved the user may well fund it before the
    price ever arrives. Both are re-checked at fill, where the answer is the one that counts.
    """
    symbol = symbol.upper()
    if limit_price <= _ZERO:
        raise InvalidOrder("Your limit price has to be more than zero.")

    shares = _size_in_shares(quantity, amount, limit_price)

    if side == "sell":
        holding = get_holding(session, account, symbol)
        held = holding.quantity if holding is not None else _ZERO
        if held <= _ZERO:
            raise InsufficientShares(f"You don't own any {symbol} to sell.")
        if shares > held:
            raise InsufficientShares(f"You only own {shares_str(held)} shares of {symbol}.")

    order = Order(
        account_id=account.id,
        symbol=symbol,
        side=side,
        quantity=shares,
        limit_price=limit_price,
        status=OPEN,
    )
    session.add(order)
    session.flush()
    return order


def cancel(session: Session, account: Account, order_id: int) -> Order:
    """Cancel one of this account's open orders. Scoped to the account, so nobody can
    cancel an order that isn't theirs."""
    order = session.scalar(
        select(Order).where(Order.id == order_id, Order.account_id == account.id)
    )
    if order is None:
        raise OrderNotFound("We couldn't find that order.")
    if order.status != OPEN:
        raise InvalidOrder(f"That order was already {order.status}.")

    order.status = CANCELLED
    order.resolved_at = _now()
    session.flush()
    return order


def sweep(session: Session, account: Account, market: QuoteProvider) -> list[Order]:
    """Settle every open order on this account whose price has arrived.

    Returns the orders that changed, so the caller can tell the user what happened while
    they were away. Oldest first, so when two orders compete for the same cash the one that
    waited longest gets it.
    """
    orders = list(
        session.scalars(
            select(Order)
            .where(Order.account_id == account.id, Order.status == OPEN)
            .order_by(Order.created_at, Order.id)
            # Lock the rows for this transaction so two concurrent sweeps (the dashboard
            # loads the portfolio and the orders list together) can't both fill one order
            # and spend the cash twice. Ignored on SQLite, which serializes writes anyway.
            .with_for_update()
        )
    )
    if not orders:
        return []

    prices: dict[str, Decimal] = {}
    for symbol in sorted({order.symbol for order in orders}):
        try:
            prices[symbol] = Decimal(str(market.get_quote(symbol).price))
        except MarketError:
            continue  # no price, no fill: we never execute on data we couldn't get

    changed: list[Order] = []
    for order in orders:
        price = prices.get(order.symbol)
        if price is None or not _has_crossed(order, price):
            continue
        changed.append(_settle(session, account, order))
    return changed


def _settle(session: Session, account: Account, order: Order) -> Order:
    """Fill a crossed order at its limit price, or cancel it if the account can't cover it.

    ``fill_buy``/``fill_sell`` check the cash and the position before they touch anything, so
    a rejection leaves no half-applied state behind and the order can simply be cancelled.
    """
    try:
        fill = fill_buy if order.side == "buy" else fill_sell
        txn = fill(session, account, order.symbol, order.quantity, order.limit_price)
    except SimError as exc:
        order.status = CANCELLED
        order.cancel_reason = str(exc)
        order.resolved_at = _now()
        session.flush()
        return order

    order.status = FILLED
    order.transaction_id = txn.id
    order.resolved_at = _now()
    session.flush()
    return order


def _has_crossed(order: Order, price: Decimal) -> bool:
    """Has the market reached the price this order was waiting for?"""
    if order.side == "buy":
        return price <= order.limit_price
    return price >= order.limit_price


def _size_in_shares(
    quantity: Decimal | None, amount: Decimal | None, limit_price: Decimal
) -> Decimal:
    """Turn either sizing into shares, rounding down so a fill never overshoots the ask."""
    if (quantity is None) == (amount is None):
        raise InvalidOrder("Enter either a share quantity or a dollar amount.")
    size = quantity if quantity is not None else amount
    if size is None or size <= _ZERO:
        raise InvalidOrder("Order size must be greater than zero.")

    if quantity is not None:
        shares = quantity.quantize(_SHARES, rounding=ROUND_DOWN)
    else:
        shares = (size / limit_price).quantize(_SHARES, rounding=ROUND_DOWN)
    if shares <= _ZERO:
        raise InvalidOrder("That's too small to be even a fraction of a share.")
    return shares


def _now() -> datetime:
    return datetime.now(UTC)
