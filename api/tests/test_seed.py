"""Tests for the demo-account seed: it funds one account and is idempotent."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import get_settings
from models import Account, User
from seed import seed_demo_account


def test_seed_creates_one_funded_account(db_session: Session) -> None:
    settings = get_settings()

    account = seed_demo_account(db_session, settings)
    db_session.commit()

    assert account.cash_balance == settings.starting_balance
    assert account.starting_balance == settings.starting_balance
    assert len(db_session.scalars(select(User)).all()) == 1
    assert len(db_session.scalars(select(Account)).all()) == 1


def test_seed_is_idempotent_and_preserves_balance(db_session: Session) -> None:
    settings = get_settings()

    first = seed_demo_account(db_session, settings)
    db_session.commit()

    # Simulate the account having spent some cash, then re-run the seed.
    first.cash_balance = Decimal("50000")
    db_session.commit()
    second = seed_demo_account(db_session, settings)
    db_session.commit()

    assert second.id == first.id
    assert second.cash_balance == Decimal("50000")  # not reset back to the start
    assert len(db_session.scalars(select(User)).all()) == 1
    assert len(db_session.scalars(select(Account)).all()) == 1
