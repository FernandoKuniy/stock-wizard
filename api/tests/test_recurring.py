"""Unit tests for recurring investments: the cadence math and the lazy sweep.

The sweep moves real balances, so the coverage is thorough: when a run is due, what one run does
to cash and holdings, that a long gap fires once rather than stacking, pausing when the cash is
gone, skipping an unpriceable symbol, and the lifecycle (place, pause, resume, remove, reset).
The market is faked so no test touches the network.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import get_settings
from models import Account, RecurringInvestment, Transaction, User
from services.market.client import MarketError, Quote
from services.sim import recurring
from services.sim.accounts import get_or_create_account
from services.sim.engine import reset
from services.sim.recurring import _advance, _advance_past


class FakeMarket:
    """A fixed-price quote source, with an optional set of symbols whose quote blows up."""

    def __init__(self, prices: dict[str, float], failing: set[str] | None = None) -> None:
        self._prices = prices
        self.failing = failing or set()

    def get_quote(self, symbol: str) -> Quote:
        symbol = symbol.upper()
        if symbol in self.failing:
            raise MarketError(f"No quote available for {symbol}.")
        price = self._prices[symbol]
        return Quote(symbol, price, 0.0, 0.0, price, price, price, price)


@pytest.fixture
def account(db_session: Session) -> Account:
    user = User(auth_id=uuid4(), email="saver@example.com")
    db_session.add(user)
    db_session.flush()
    acct, _ = get_or_create_account(
        db_session, user, starting_balance=get_settings().starting_balance
    )
    return acct


def _transactions(session: Session, account: Account) -> list[Transaction]:
    return list(session.scalars(select(Transaction).where(Transaction.account_id == account.id)))


# --- cadence math ------------------------------------------------------------------------


def test_weekly_advances_seven_days() -> None:
    assert _advance(date(2026, 8, 13), "weekly") == date(2026, 8, 20)


def test_monthly_keeps_the_day_of_month() -> None:
    assert _advance(date(2026, 8, 15), "monthly") == date(2026, 9, 15)


def test_monthly_clamps_to_a_short_months_end() -> None:
    # Jan 31 has no Feb 31, so it lands on the last day of February.
    assert _advance(date(2026, 1, 31), "monthly") == date(2026, 2, 28)


def test_monthly_rolls_over_the_year() -> None:
    assert _advance(date(2026, 12, 10), "monthly") == date(2027, 1, 10)


def test_advance_past_skips_a_whole_backlog_to_the_next_future_date() -> None:
    # Due since January, viewed in August: the next run is next month, not a pile of missed ones.
    assert _advance_past(date(2026, 1, 1), "monthly", date(2026, 8, 13)) == date(2026, 9, 1)


# --- the sweep ---------------------------------------------------------------------------


def test_a_due_run_buys_at_the_latest_quote_and_advances(
    db_session: Session, account: Account
) -> None:
    recurring.place(
        db_session,
        account,
        "AAPL",
        amount=Decimal("600"),
        cadence="monthly",
        today=date(2026, 8, 1),
    )
    market = FakeMarket({"AAPL": 150.0})

    changed = recurring.sweep(db_session, account, market, today=date(2026, 8, 1))

    assert len(changed) == 1
    schedule = changed[0]
    assert schedule.last_run_on == date(2026, 8, 1)
    assert schedule.next_run_on == date(2026, 9, 1)  # advanced by one month
    assert schedule.active is True
    # $600 at $150 bought 4 shares and left the cash down by exactly $600.
    txns = _transactions(db_session, account)
    assert len(txns) == 1
    assert txns[0].symbol == "AAPL"
    assert txns[0].quantity == Decimal("4.000000")
    assert account.cash_balance == get_settings().starting_balance - Decimal("600")


def test_a_run_that_is_not_due_yet_does_nothing(db_session: Session, account: Account) -> None:
    recurring.place(
        db_session,
        account,
        "AAPL",
        amount=Decimal("600"),
        cadence="monthly",
        today=date(2026, 9, 1),
    )
    market = FakeMarket({"AAPL": 150.0})

    assert recurring.sweep(db_session, account, market, today=date(2026, 8, 1)) == []
    assert _transactions(db_session, account) == []


def test_a_long_gap_fires_once_not_a_pile(db_session: Session, account: Account) -> None:
    schedule = recurring.place(
        db_session,
        account,
        "AAPL",
        amount=Decimal("600"),
        cadence="monthly",
        today=date(2026, 1, 1),
    )
    schedule.next_run_on = date(2026, 1, 1)  # away since January
    db_session.flush()
    market = FakeMarket({"AAPL": 150.0})

    recurring.sweep(db_session, account, market, today=date(2026, 8, 13))

    # One buy, not eight, and the schedule realigns to the next future month.
    assert len(_transactions(db_session, account)) == 1
    assert schedule.next_run_on == date(2026, 9, 1)


def test_a_run_the_account_cannot_afford_pauses_with_a_reason(
    db_session: Session, account: Account
) -> None:
    account.cash_balance = Decimal("100")  # not enough for a $600 buy
    schedule = recurring.place(
        db_session,
        account,
        "AAPL",
        amount=Decimal("600"),
        cadence="monthly",
        today=date(2026, 8, 1),
    )
    db_session.flush()
    market = FakeMarket({"AAPL": 150.0})

    changed = recurring.sweep(db_session, account, market, today=date(2026, 8, 1))

    assert len(changed) == 1
    assert schedule.active is False
    assert schedule.paused_reason is not None
    assert schedule.next_run_on == date(2026, 8, 1)  # not advanced; nothing was bought
    assert account.cash_balance == Decimal("100")  # untouched
    assert _transactions(db_session, account) == []


def test_a_paused_schedule_does_not_fire(db_session: Session, account: Account) -> None:
    schedule = recurring.place(
        db_session,
        account,
        "AAPL",
        amount=Decimal("600"),
        cadence="monthly",
        today=date(2026, 8, 1),
    )
    recurring.set_active(db_session, account, schedule.id, active=False)
    market = FakeMarket({"AAPL": 150.0})

    assert recurring.sweep(db_session, account, market, today=date(2026, 8, 1)) == []


def test_a_symbol_that_cannot_be_priced_is_left_to_try_again(
    db_session: Session, account: Account
) -> None:
    schedule = recurring.place(
        db_session,
        account,
        "AAPL",
        amount=Decimal("600"),
        cadence="monthly",
        today=date(2026, 8, 1),
    )
    market = FakeMarket({"AAPL": 150.0}, failing={"AAPL"})

    assert recurring.sweep(db_session, account, market, today=date(2026, 8, 1)) == []
    # Left due and active, so the next load can try again; nothing bought, nothing paused.
    assert schedule.active is True
    assert schedule.next_run_on == date(2026, 8, 1)
    assert _transactions(db_session, account) == []


# --- lifecycle ---------------------------------------------------------------------------


def test_place_makes_the_first_run_due_today(db_session: Session, account: Account) -> None:
    schedule = recurring.place(
        db_session,
        account,
        "aapl",
        amount=Decimal("500"),
        cadence="weekly",
        today=date(2026, 8, 13),
    )
    assert schedule.symbol == "AAPL"
    assert schedule.next_run_on == date(2026, 8, 13)
    assert schedule.active is True


def test_place_rejects_a_bad_amount_or_cadence(db_session: Session, account: Account) -> None:
    with pytest.raises(recurring.RecurringError):
        recurring.place(db_session, account, "AAPL", amount=Decimal("0"), cadence="monthly")
    with pytest.raises(recurring.RecurringError):
        recurring.place(db_session, account, "AAPL", amount=Decimal("500"), cadence="daily")  # type: ignore[arg-type]


def test_resume_clears_the_reason_and_makes_it_due_again(
    db_session: Session, account: Account
) -> None:
    schedule = recurring.place(
        db_session,
        account,
        "AAPL",
        amount=Decimal("600"),
        cadence="monthly",
        today=date(2026, 8, 1),
    )
    schedule.active = False
    schedule.paused_reason = "ran out of cash"
    db_session.flush()

    recurring.set_active(db_session, account, schedule.id, active=True, today=date(2026, 8, 20))

    assert schedule.active is True
    assert schedule.paused_reason is None
    assert schedule.next_run_on == date(2026, 8, 20)


def test_remove_deletes_the_schedule(db_session: Session, account: Account) -> None:
    schedule = recurring.place(db_session, account, "AAPL", amount=Decimal("500"), cadence="weekly")

    recurring.remove(db_session, account, schedule.id)

    assert db_session.scalars(select(RecurringInvestment)).all() == []


def test_a_missing_schedule_raises(db_session: Session, account: Account) -> None:
    with pytest.raises(recurring.RecurringNotFound):
        recurring.remove(db_session, account, 999)


def test_reset_clears_schedules(db_session: Session, account: Account) -> None:
    recurring.place(db_session, account, "AAPL", amount=Decimal("500"), cadence="weekly")

    reset(db_session, account)

    assert db_session.scalars(select(RecurringInvestment)).all() == []


def test_one_accounts_schedules_are_invisible_to_another(db_session: Session) -> None:
    settings = get_settings()
    alex = User(auth_id=uuid4(), email="alex@example.com")
    sam = User(auth_id=uuid4(), email="sam@example.com")
    db_session.add_all([alex, sam])
    db_session.flush()
    alex_acct, _ = get_or_create_account(
        db_session, alex, starting_balance=settings.starting_balance
    )
    sam_acct, _ = get_or_create_account(db_session, sam, starting_balance=settings.starting_balance)
    schedule = recurring.place(
        db_session, alex_acct, "AAPL", amount=Decimal("500"), cadence="weekly"
    )

    # Sam can't touch Alex's schedule.
    with pytest.raises(recurring.RecurringNotFound):
        recurring.remove(db_session, sam_acct, schedule.id)
    assert recurring.sweep(db_session, sam_acct, FakeMarket({"AAPL": 150.0})) == []
