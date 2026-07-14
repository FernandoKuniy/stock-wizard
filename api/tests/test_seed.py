"""Tests for account provisioning: one funded account per user, and the seed script."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import get_settings
from models import Account, User
from seed import SeedError, seed_account
from services.sim.accounts import get_or_create_account


def make_user(session: Session, email: str = "learner@example.com") -> User:
    user = User(auth_id=uuid4(), email=email)
    session.add(user)
    session.flush()
    return user


def test_opens_one_funded_account(db_session: Session) -> None:
    settings = get_settings()
    user = make_user(db_session)

    account, created = get_or_create_account(
        db_session, user, starting_balance=settings.starting_balance
    )
    db_session.commit()

    assert created is True
    assert account.cash_balance == settings.starting_balance
    assert account.starting_balance == settings.starting_balance
    assert len(db_session.scalars(select(Account)).all()) == 1


def test_is_idempotent_and_preserves_balance(db_session: Session) -> None:
    settings = get_settings()
    user = make_user(db_session)

    first, _ = get_or_create_account(db_session, user, starting_balance=settings.starting_balance)
    db_session.commit()

    # Simulate the account having spent some cash, then ask for it again.
    first.cash_balance = Decimal("50000")
    db_session.commit()
    second, created = get_or_create_account(
        db_session, user, starting_balance=settings.starting_balance
    )
    db_session.commit()

    assert created is False
    assert second.id == first.id
    assert second.cash_balance == Decimal("50000")  # not reset back to the start
    assert len(db_session.scalars(select(Account)).all()) == 1


def test_each_user_gets_their_own_account(db_session: Session) -> None:
    settings = get_settings()
    alex = make_user(db_session, "alex@example.com")
    sam = make_user(db_session, "sam@example.com")

    alex_account, _ = get_or_create_account(
        db_session, alex, starting_balance=settings.starting_balance
    )
    sam_account, _ = get_or_create_account(
        db_session, sam, starting_balance=settings.starting_balance
    )
    db_session.commit()

    assert alex_account.id != sam_account.id
    assert len(db_session.scalars(select(Account)).all()) == 2


def test_seed_funds_a_signed_up_user(db_session: Session) -> None:
    settings = get_settings()
    make_user(db_session, "alex@example.com")
    db_session.commit()

    account, created = seed_account(db_session, "alex@example.com", settings)
    db_session.commit()

    assert created is True
    assert account.cash_balance == settings.starting_balance


def test_seed_explains_itself_when_the_user_has_not_signed_up(db_session: Session) -> None:
    with pytest.raises(SeedError, match="Sign up in the web app first"):
        seed_account(db_session, "nobody@example.com", get_settings())
