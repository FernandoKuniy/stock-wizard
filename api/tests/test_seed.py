"""Tests for account provisioning: one funded account per user, and the seed script."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import get_settings
from models import Account, Transaction, User
from seed import DEMO_BUYS, SeedError, seed_account, seed_history
from services.market.candles import CandlePoint, Candles
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


def test_seed_ignores_a_leftover_pre_auth_row_with_the_same_email(db_session: Session) -> None:
    # Accounts created before auth have no auth_id and nobody can sign in as them. They can
    # also share an email with a real user, since Supabase owns email uniqueness now, not us.
    legacy = User(auth_id=None, email="alex@example.com")
    db_session.add(legacy)
    db_session.flush()
    signed_up = make_user(db_session, "alex@example.com")
    db_session.commit()

    account, _ = seed_account(db_session, "alex@example.com", get_settings())

    # The money has to land in the account the human can actually reach.
    assert account.user_id == signed_up.id
    assert account.user_id != legacy.id


class FakeCandles:
    """A year of daily bars at a flat $100, so the arithmetic is easy to check."""

    def get_candles(self, symbol: str, *, outputsize: int = 90) -> Candles:
        today = datetime.now(UTC).date()
        points = [
            CandlePoint((today - timedelta(days=offset)).isoformat(), 100.0)
            for offset in reversed(range(365))
        ]
        return Candles(symbol.upper(), points)


def funded_account(db_session: Session) -> Account:
    user = make_user(db_session)
    account, _ = get_or_create_account(
        db_session, user, starting_balance=get_settings().starting_balance
    )
    return account


def test_history_buys_the_demo_holdings_at_their_historical_prices(db_session: Session) -> None:
    account = funded_account(db_session)

    trades = seed_history(db_session, account, FakeCandles())
    db_session.commit()

    # DEMO_BUYS is listed oldest first, and the trades are written in the order they
    # happened, so the two line up.
    assert [t.symbol for t in trades] == [symbol for symbol, _, _ in DEMO_BUYS]
    # $75k of the $100k gets invested, at $100 a share.
    spent = sum(dollars for _, dollars, _ in DEMO_BUYS)
    assert account.cash_balance == get_settings().starting_balance - spent
    for trade, (_, dollars, _) in zip(trades, DEMO_BUYS, strict=True):
        assert trade.price == Decimal("100")
        assert trade.quantity == dollars / Decimal("100")


def test_history_is_ordered_oldest_first_and_predates_the_account(db_session: Session) -> None:
    account = funded_account(db_session)

    trades = seed_history(db_session, account, FakeCandles())
    db_session.commit()

    timestamps = [t.timestamp for t in trades]
    assert timestamps == sorted(timestamps)
    # The account has to look older than its oldest trade, or the chart would start
    # after the money was already invested.
    assert account.created_at.date() < timestamps[0].date()


def test_history_refuses_to_double_up(db_session: Session) -> None:
    account = funded_account(db_session)
    seed_history(db_session, account, FakeCandles())
    db_session.commit()

    with pytest.raises(SeedError, match="already has trades"):
        seed_history(db_session, account, FakeCandles())


def test_history_leaves_a_traded_account_alone(db_session: Session) -> None:
    account = funded_account(db_session)
    db_session.add(
        Transaction(
            account_id=account.id,
            symbol="AAPL",
            side="buy",
            quantity=Decimal("1"),
            price=Decimal("150"),
            timestamp=datetime.now(UTC),
        )
    )
    db_session.flush()

    with pytest.raises(SeedError, match="already has trades"):
        seed_history(db_session, account, FakeCandles())


def test_history_says_so_when_it_cannot_reach_that_far_back(db_session: Session) -> None:
    account = funded_account(db_session)

    class ShortCandles:
        """Only a week of bars: nowhere near the six months the demo history needs."""

        def get_candles(self, symbol: str, *, outputsize: int = 90) -> Candles:
            today = date.today()
            points = [
                CandlePoint((today - timedelta(days=offset)).isoformat(), 100.0)
                for offset in reversed(range(7))
            ]
            return Candles(symbol.upper(), points)

    with pytest.raises(SeedError, match="on or before"):
        seed_history(db_session, account, ShortCandles())
