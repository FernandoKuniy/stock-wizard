"""The paper-trading engine: buy, sell, and reset.

Market orders fill at the latest quote. An order can be sized either by share
quantity or by dollar amount; when it is a dollar amount we work out the shares
here, in code, at the current price (hard rule #1: numbers come from code).
Shares are held to 6 decimals and money to 4, matching the database columns.

These functions mutate and ``flush`` the session but never ``commit``: the caller
(a route handler) owns the transaction boundary. Every failure is a typed
``SimError`` whose message is safe to show a user; market and network failures
stay as ``MarketError`` and bubble up untouched.

``fill_buy`` and ``fill_sell`` are the settlement primitives: given shares and a
price, they move the cash and the holding and write the transaction. Everything
that can fill an order goes through them, so the money math lives in exactly one
place and cannot drift. Today that means market orders (here), the seed script's
backfill, and the limit-order sweep in ``services/sim/orders.py``.
"""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from models import Account, Holding, Order, Transaction
from services.market.client import Quote

_SHARES = Decimal("0.000001")  # 6dp, matches holdings.quantity
_CASH = Decimal("0.0001")  # 4dp, matches the money columns
_ZERO = Decimal(0)


class QuoteProvider(Protocol):
    """The slice of the market client the sim needs: a latest quote."""

    def get_quote(self, symbol: str) -> Quote: ...


class SimError(Exception):
    """A trade could not be completed. The message is safe to show a user."""


class InvalidOrder(SimError):
    """The order size was missing, non-positive, or too small to fill."""


class InsufficientFunds(SimError):
    """Not enough cash to cover the buy."""


class InsufficientShares(SimError):
    """Not enough shares held to cover the sell."""


def buy(
    session: Session,
    account: Account,
    symbol: str,
    *,
    quantity: Decimal | None = None,
    amount: Decimal | None = None,
    market: QuoteProvider,
) -> Transaction:
    """Buy ``symbol`` by share quantity or dollar amount, filling at the latest quote."""
    symbol = symbol.upper()
    size = _require_one_size(quantity, amount)

    price = Decimal(str(market.get_quote(symbol).price))
    if quantity is not None:
        shares = quantity.quantize(_SHARES, rounding=ROUND_DOWN)
    else:
        shares = (size / price).quantize(_SHARES, rounding=ROUND_DOWN)

    return fill_buy(session, account, symbol, shares, price)


def backfill_buy(
    session: Session,
    account: Account,
    symbol: str,
    *,
    shares: Decimal,
    price: Decimal,
    at: datetime,
) -> Transaction:
    """Record a buy that happened in the past, filled at that day's closing price.

    This exists for the seed script, which gives a demo account real history so the
    benchmark chart has a curve worth teaching from. It is not a back door into the
    trading API: no route calls it, and a live order always goes through ``buy``, which
    fills at the latest quote and cannot be handed a price. The cash, average-cost, and
    transaction bookkeeping is the same code either way.
    """
    return fill_buy(
        session, account, symbol.upper(), shares.quantize(_SHARES, rounding=ROUND_DOWN), price, at
    )


def sell(
    session: Session,
    account: Account,
    symbol: str,
    *,
    quantity: Decimal | None = None,
    amount: Decimal | None = None,
    market: QuoteProvider,
) -> Transaction:
    """Sell ``symbol`` by share quantity or dollar amount, filling at the latest quote."""
    symbol = symbol.upper()
    size = _require_one_size(quantity, amount)

    holding = get_holding(session, account, symbol)
    if holding is None or holding.quantity <= _ZERO:
        raise InsufficientShares(f"You don't own any {symbol} to sell.")

    price = Decimal(str(market.get_quote(symbol).price))
    if quantity is not None:
        shares = quantity.quantize(_SHARES, rounding=ROUND_DOWN)
    else:
        # A dollar-sized sell caps at the position rather than overshooting it.
        shares = min((size / price).quantize(_SHARES, rounding=ROUND_DOWN), holding.quantity)

    return fill_sell(session, account, symbol, shares, price)


def reset(session: Session, account: Account) -> None:
    """Wipe the slate: restore the starting cash, delete holdings, orders, and transactions.

    Orders go first: a filled one points at the transaction it became, so the trades cannot
    be deleted out from under it. The watchlist deliberately survives a reset, since it is a
    list of things to look at rather than anything to do with money.
    """
    session.execute(
        delete(Order)
        .where(Order.account_id == account.id)
        .execution_options(synchronize_session=False)
    )
    session.execute(
        delete(Transaction)
        .where(Transaction.account_id == account.id)
        .execution_options(synchronize_session=False)
    )
    session.execute(
        delete(Holding)
        .where(Holding.account_id == account.id)
        .execution_options(synchronize_session=False)
    )
    account.cash_balance = account.starting_balance
    session.flush()


def fill_buy(
    session: Session,
    account: Account,
    symbol: str,
    shares: Decimal,
    price: Decimal,
    at: datetime | None = None,
) -> Transaction:
    """Settle a buy of ``shares`` at ``price``: check the cash, debit it, book the shares.

    One of the two settlement primitives (see the module docstring). Market orders, the
    seed backfill, and the limit-order sweep all land here, so a fill is bookkept the same
    way no matter what triggered it.
    """
    if shares <= _ZERO:
        raise InvalidOrder("That's too small to buy even a fraction of a share.")

    cost = (shares * price).quantize(_CASH, rounding=ROUND_HALF_UP)
    if cost > account.cash_balance:
        raise InsufficientFunds(
            f"You need ${_money(cost)} but only have ${_money(account.cash_balance)}."
        )

    account.cash_balance -= cost
    _add_shares(session, account, symbol, shares, cost)

    return _record(session, account, symbol, "buy", shares, price, at=at)


def fill_sell(
    session: Session,
    account: Account,
    symbol: str,
    shares: Decimal,
    price: Decimal,
    at: datetime | None = None,
) -> Transaction:
    """Settle a sell of ``shares`` at ``price``: check the shares, credit the cash, book it.

    The mirror of ``fill_buy``. It re-checks the position itself rather than trusting the
    caller, because the limit sweep can reach it long after the order was placed, by which
    time the shares may be gone.
    """
    if shares <= _ZERO:
        raise InvalidOrder("That's too small to sell even a fraction of a share.")

    holding = get_holding(session, account, symbol)
    if holding is None or holding.quantity <= _ZERO:
        raise InsufficientShares(f"You don't own any {symbol} to sell.")
    if shares > holding.quantity:
        raise InsufficientShares(f"You only own {shares_str(holding.quantity)} shares of {symbol}.")

    proceeds = (shares * price).quantize(_CASH, rounding=ROUND_HALF_UP)
    account.cash_balance += proceeds

    if holding.quantity - shares <= _ZERO:
        session.delete(holding)
    else:
        holding.quantity -= shares

    return _record(session, account, symbol, "sell", shares, price, at=at)


def _require_one_size(quantity: Decimal | None, amount: Decimal | None) -> Decimal:
    """Validate that exactly one positive size was given, and return it."""
    if (quantity is None) == (amount is None):
        raise InvalidOrder("Enter either a share quantity or a dollar amount.")
    size = quantity if quantity is not None else amount
    if size is None or size <= _ZERO:
        raise InvalidOrder("Order size must be greater than zero.")
    return size


def get_holding(session: Session, account: Account, symbol: str) -> Holding | None:
    return session.scalar(
        select(Holding).where(Holding.account_id == account.id, Holding.symbol == symbol)
    )


def _add_shares(
    session: Session, account: Account, symbol: str, shares: Decimal, cost: Decimal
) -> None:
    """Add bought shares to the holding, recomputing the weighted average cost."""
    holding = get_holding(session, account, symbol)
    if holding is None:
        avg_cost = (cost / shares).quantize(_CASH, rounding=ROUND_HALF_UP)
        session.add(
            Holding(account_id=account.id, symbol=symbol, quantity=shares, avg_cost=avg_cost)
        )
        return
    new_quantity = holding.quantity + shares
    new_basis = holding.quantity * holding.avg_cost + cost
    holding.quantity = new_quantity
    holding.avg_cost = (new_basis / new_quantity).quantize(_CASH, rounding=ROUND_HALF_UP)


def _record(
    session: Session,
    account: Account,
    symbol: str,
    side: str,
    shares: Decimal,
    price: Decimal,
    at: datetime | None = None,
) -> Transaction:
    """Write the transaction row and flush so it gets an id and timestamp.

    ``at`` overrides the database's "now" default, which only the seed script needs.
    """
    txn = Transaction(account_id=account.id, symbol=symbol, side=side, quantity=shares, price=price)
    if at is not None:
        txn.timestamp = at
    session.add(txn)
    session.flush()
    return txn


def _money(value: Decimal) -> str:
    return f"{value:.2f}"


def shares_str(value: Decimal) -> str:
    return f"{value.normalize():f}"
