"""Order routes: place a market or limit order, list resting orders, cancel one, and the ledger.

The money math lives in the sim layer; these routes translate HTTP in and out and own the
transaction boundary. ``_sweep_orders`` is shared with the portfolio router, which settles
resting orders on the same lazy, no-cron schedule when the user loads their dashboard.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Account, Order, Transaction
from routers.common import AccountDep, MarketDep, SessionDep, _round2, _shares
from schemas import OrderOut, OrderRequest, OrderResultOut, TransactionOut
from services.market.client import MarketClient, MarketError
from services.sim import orders as sim_orders
from services.sim.engine import SimError, buy, sell

router = APIRouter()


@router.post("/api/orders")
def create_order(
    body: OrderRequest, account: AccountDep, session: SessionDep, market: MarketDep
) -> OrderResultOut:
    """Place a buy or sell, sized by shares or dollars.

    A market order fills now, at the latest quote, and comes back as a transaction. A limit
    order rests until the price arrives and comes back as an order; placing one spends no
    quote quota, since nothing is priced until it fills.
    """
    if body.type == "limit":
        return _place_limit_order(session, account, body)

    try:
        txn = _execute_order(session, account, body, market)
    except SimError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MarketError as exc:
        session.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    session.commit()
    session.refresh(txn)  # populate the server-side timestamp
    return OrderResultOut(transaction=_txn_out(txn), cash=_round2(account.cash_balance))


@router.get("/api/orders")
def read_orders(account: AccountDep, session: SessionDep, market: MarketDep) -> list[OrderOut]:
    """The account's limit orders, newest first, after settling any whose price has arrived."""
    _sweep_orders(session, account, market)
    rows = session.scalars(
        select(Order)
        .where(Order.account_id == account.id)
        .order_by(Order.created_at.desc(), Order.id.desc())
    )
    return [_order_out(order) for order in rows]


@router.delete("/api/orders/{order_id}")
def cancel_order(order_id: int, account: AccountDep, session: SessionDep) -> OrderOut:
    """Cancel one of your resting limit orders."""
    try:
        order = sim_orders.cancel(session, account, order_id)
    except sim_orders.OrderNotFound as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SimError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    return _order_out(order)


@router.get("/api/transactions")
def read_transactions(account: AccountDep, session: SessionDep) -> list[TransactionOut]:
    """The full transaction history, newest first."""
    rows = session.scalars(
        select(Transaction)
        .where(Transaction.account_id == account.id)
        .order_by(Transaction.timestamp.desc(), Transaction.id.desc())
    )
    return [_txn_out(t) for t in rows]


def _sweep_orders(session: Session, account: Account, market: MarketClient) -> None:
    """Settle any resting limit orders whose price has arrived.

    This is the app's stand-in for a background job: orders get looked at when the user
    looks at their money. Committing inside a GET is deliberate, because a fill is a real
    change to the account, not a read. A symbol we can't price is skipped, never filled.
    """
    if sim_orders.sweep(session, account, market):
        session.commit()


def _place_limit_order(session: Session, account: Account, body: OrderRequest) -> OrderResultOut:
    """Rest a limit order. No quote is needed: nothing is priced until it fills."""
    if body.limit_price is None:
        raise HTTPException(status_code=400, detail="A limit order needs a limit price.")
    try:
        order = sim_orders.place(
            session,
            account,
            body.symbol,
            side=body.side,
            limit_price=body.limit_price,
            quantity=body.value if body.mode == "shares" else None,
            amount=body.value if body.mode == "dollars" else None,
        )
    except SimError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    session.refresh(order)  # populate the server-side timestamp
    return OrderResultOut(order=_order_out(order), cash=_round2(account.cash_balance))


def _execute_order(
    session: Session, account: Account, body: OrderRequest, market: MarketClient
) -> Transaction:
    if body.side == "buy":
        if body.mode == "shares":
            return buy(session, account, body.symbol, quantity=body.value, market=market)
        return buy(session, account, body.symbol, amount=body.value, market=market)
    if body.mode == "shares":
        return sell(session, account, body.symbol, quantity=body.value, market=market)
    return sell(session, account, body.symbol, amount=body.value, market=market)


def _order_out(order: Order) -> OrderOut:
    return OrderOut(
        id=order.id,
        symbol=order.symbol,
        side=order.side,
        quantity=_shares(order.quantity),
        limit_price=_round2(order.limit_price),
        status=order.status,
        created_at=order.created_at,
        resolved_at=order.resolved_at,
        cancel_reason=order.cancel_reason,
    )


def _txn_out(txn: Transaction) -> TransactionOut:
    return TransactionOut(
        id=txn.id,
        symbol=txn.symbol,
        side=txn.side,
        quantity=_shares(txn.quantity),
        price=_round2(txn.price),
        total=_round2(txn.quantity * txn.price),
        timestamp=txn.timestamp,
    )
