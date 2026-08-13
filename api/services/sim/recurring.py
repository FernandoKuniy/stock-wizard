"""Recurring investments: automating a fixed buy on a schedule (dollar-cost averaging).

A schedule says "put $X into this stock every week/month". This app runs no background job, so
like the limit-order sweep it settles lazily: when the user loads their dashboard, ``sweep``
fires every schedule whose next run has come due, buying at the latest quote through the same
``engine.buy`` a manual order uses, so the money math lives in one place.

Two deliberate rules, both about being honest inside a no-cron sim:

- **One run per load, then realign to the future.** If several runs came due while the user was
  away, we don't stack them into a pile of identical same-price buys: we fire once and move
  ``next_run_on`` to the next date after today. A missed stretch is skipped, not caught up, which
  matches the fact that we can only ever fill at the price we can see now. The dollar-cost-average
  *lesson* (buying across many prices) lives in the what-if calculator; this feature is the habit.
- **Pause, never overdraw.** A run the account can't afford pauses the schedule with a reason
  rather than part-filling or going negative. The user can add cash and resume it.

Like the rest of the sim, these functions flush but never commit: the caller owns the boundary.
"""

from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Account, RecurringInvestment
from services.market.client import MarketError
from services.sim.engine import InsufficientFunds, InvalidOrder, QuoteProvider, SimError, buy

WEEKLY = "weekly"
MONTHLY = "monthly"
Cadence = Literal["weekly", "monthly"]

_ZERO = Decimal(0)


class RecurringError(SimError):
    """The schedule couldn't be set up. The message is safe to show a user."""


class RecurringNotFound(SimError):
    """No such schedule on this account."""


def place(
    session: Session,
    account: Account,
    symbol: str,
    *,
    amount: Decimal,
    cadence: Cadence,
    today: date | None = None,
) -> RecurringInvestment:
    """Set up a schedule. The first run is due today, so it fires on the next dashboard load.

    The symbol is validated by the caller against a live quote (a junk ticker is never stored),
    the same way a watchlist add is; nothing is bought here, so no cash moves until the sweep.
    """
    if cadence not in (WEEKLY, MONTHLY):
        raise RecurringError("Choose weekly or monthly.")
    if amount <= _ZERO:
        raise RecurringError("The amount has to be more than zero.")

    schedule = RecurringInvestment(
        account_id=account.id,
        symbol=symbol.upper(),
        amount=amount,
        cadence=cadence,
        next_run_on=today or _today(),
        active=True,
    )
    session.add(schedule)
    session.flush()
    return schedule


def set_active(
    session: Session,
    account: Account,
    schedule_id: int,
    *,
    active: bool,
    today: date | None = None,
) -> RecurringInvestment:
    """Pause or resume one of this account's schedules.

    Resuming clears any pause reason and makes the next run due today, so an account that paused
    because it ran out of cash starts again on the next load once there's money to cover it.
    """
    schedule = _get(session, account, schedule_id)
    schedule.active = active
    schedule.paused_reason = None
    if active:
        schedule.next_run_on = today or _today()
    session.flush()
    return schedule


def remove(session: Session, account: Account, schedule_id: int) -> None:
    """Cancel one of this account's schedules for good."""
    session.delete(_get(session, account, schedule_id))
    session.flush()


def sweep(
    session: Session,
    account: Account,
    market: QuoteProvider,
    *,
    today: date | None = None,
) -> list[RecurringInvestment]:
    """Fire every active schedule whose next run has come due, and return the ones that changed.

    Each due schedule fires once, at the latest quote, then realigns to its next future run. A
    schedule the account can't afford pauses; one whose symbol can't be priced right now is left
    untouched to try again on the next load.
    """
    on = today or _today()
    schedules = list(
        session.scalars(
            select(RecurringInvestment)
            .where(
                RecurringInvestment.account_id == account.id,
                RecurringInvestment.active.is_(True),
                RecurringInvestment.next_run_on <= on,
            )
            .order_by(RecurringInvestment.created_at, RecurringInvestment.id)
            # Lock the rows so two concurrent sweeps (the dashboard loads several things at once)
            # can't fire the same run twice. Ignored on SQLite, which serializes writes anyway.
            .with_for_update()
        )
    )

    changed: list[RecurringInvestment] = []
    for schedule in schedules:
        if _run_once(session, account, schedule, market, on):
            changed.append(schedule)
    return changed


def _run_once(
    session: Session,
    account: Account,
    schedule: RecurringInvestment,
    market: QuoteProvider,
    today: date,
) -> bool:
    """Fire one due run of ``schedule``, or pause it. Returns whether the schedule changed."""
    try:
        buy(session, account, schedule.symbol, amount=schedule.amount, market=market)
    except (InsufficientFunds, InvalidOrder):
        schedule.active = False
        schedule.paused_reason = (
            f"Paused: your {_money(schedule.amount)} automatic buy that came due on "
            f"{schedule.next_run_on.isoformat()} was more than your cash. Add cash and resume it."
        )
        session.flush()
        return True
    except MarketError:
        return False  # can't price it now; leave it due and try again next load

    schedule.last_run_on = today
    schedule.next_run_on = _advance_past(schedule.next_run_on, schedule.cadence, today)
    session.flush()
    return True


def _advance_past(on: date, cadence: str, today: date) -> date:
    """The next run date strictly after today, stepping by the cadence from ``on``."""
    nxt = _advance(on, cadence)
    while nxt <= today:
        nxt = _advance(nxt, cadence)
    return nxt


def _advance(on: date, cadence: str) -> date:
    """One cadence step forward. Monthly keeps the day of month, clamped to a short month's end."""
    if cadence == WEEKLY:
        return on + timedelta(days=7)
    month = on.month + 1
    year = on.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(on.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _get(session: Session, account: Account, schedule_id: int) -> RecurringInvestment:
    schedule = session.scalar(
        select(RecurringInvestment).where(
            RecurringInvestment.id == schedule_id,
            RecurringInvestment.account_id == account.id,
        )
    )
    if schedule is None:
        raise RecurringNotFound("We couldn't find that automatic investment.")
    return schedule


def _today() -> date:
    return datetime.now(UTC).date()


def _money(value: Decimal) -> str:
    return f"${value:.2f}"
