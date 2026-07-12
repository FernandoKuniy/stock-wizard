"""Seed the single demo account.

Until real auth lands in M2 the app has exactly one user and one funded account.
This script is idempotent: run it as many times as you like and it creates the
pair once, never resetting an existing balance.

Run it with: ``uv run python -m seed``
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import Settings, get_settings
from db import SessionLocal
from models import Account, User


def seed_demo_account(session: Session, settings: Settings) -> Account:
    """Ensure the demo user and their funded account exist, and return the account."""
    user = session.scalar(select(User).where(User.email == settings.seed_user_email))
    if user is None:
        user = User(email=settings.seed_user_email)
        session.add(user)
        session.flush()  # assigns user.id

    account = session.scalar(select(Account).where(Account.user_id == user.id))
    if account is None:
        account = Account(
            user_id=user.id,
            cash_balance=settings.starting_balance,
            starting_balance=settings.starting_balance,
        )
        session.add(account)
        session.flush()  # assigns account.id

    return account


def main() -> None:
    """Seed the account against the real database and report what happened."""
    settings = get_settings()
    with SessionLocal() as session:
        account = seed_demo_account(session, settings)
        session.commit()
        print(f"Demo account ready: id={account.id}, cash={account.cash_balance}")


if __name__ == "__main__":
    main()
