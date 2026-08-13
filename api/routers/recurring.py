"""Recurring-investment routes: set up, list, pause/resume, and cancel an automatic buy.

The money math and the schedule lifecycle live in ``services/sim/recurring.py``; these routes
translate HTTP in and out and own the transaction boundary. The buys themselves happen in the
sweep on dashboard load (see the portfolio router), not here: setting one up spends no cash.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from models import RecurringInvestment
from routers.common import AccountDep, MarketDep, SessionDep, _round2
from schemas import RecurringOut, RecurringRequest, RecurringUpdate
from services.market.client import MarketError
from services.sim import recurring as sim_recurring
from services.sim.engine import SimError

router = APIRouter()


@router.post("/api/recurring")
def create_recurring(
    body: RecurringRequest, account: AccountDep, session: SessionDep, market: MarketDep
) -> RecurringOut:
    """Set up an automatic investment. The first buy fires on your next dashboard load.

    The symbol is validated against a live quote first, so a junk ticker is never stored, the
    same as a watchlist add. No cash moves here: nothing is bought until the schedule comes due.
    """
    symbol = body.symbol.strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="Enter a symbol to invest in.")
    try:
        market.get_quote(symbol)
    except MarketError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        schedule = sim_recurring.place(
            session, account, symbol, amount=body.amount, cadence=body.cadence
        )
    except SimError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    session.refresh(schedule)  # populate the server-side created_at
    return _recurring_out(schedule)


@router.get("/api/recurring")
def read_recurring(account: AccountDep, session: SessionDep) -> list[RecurringOut]:
    """This account's automatic investments, newest first. A pure read; no buys happen here."""
    rows = session.scalars(
        select(RecurringInvestment)
        .where(RecurringInvestment.account_id == account.id)
        .order_by(RecurringInvestment.created_at.desc(), RecurringInvestment.id.desc())
    )
    return [_recurring_out(schedule) for schedule in rows]


@router.patch("/api/recurring/{schedule_id}")
def update_recurring(
    schedule_id: int, body: RecurringUpdate, account: AccountDep, session: SessionDep
) -> RecurringOut:
    """Pause or resume an automatic investment. Resuming makes the next buy due on the next load."""
    try:
        schedule = sim_recurring.set_active(session, account, schedule_id, active=body.active)
    except sim_recurring.RecurringNotFound as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    session.commit()
    return _recurring_out(schedule)


@router.delete("/api/recurring/{schedule_id}", status_code=204)
def delete_recurring(schedule_id: int, account: AccountDep, session: SessionDep) -> None:
    """Cancel an automatic investment for good."""
    try:
        sim_recurring.remove(session, account, schedule_id)
    except sim_recurring.RecurringNotFound as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    session.commit()


def _recurring_out(schedule: RecurringInvestment) -> RecurringOut:
    return RecurringOut(
        id=schedule.id,
        symbol=schedule.symbol,
        amount=_round2(schedule.amount),
        cadence=schedule.cadence,
        next_run_on=schedule.next_run_on,
        last_run_on=schedule.last_run_on,
        active=schedule.active,
        paused_reason=schedule.paused_reason,
        created_at=schedule.created_at,
    )
