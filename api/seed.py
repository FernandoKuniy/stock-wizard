"""Fund a signed-up user's paper-trading account.

Accounts open themselves: the first time someone signs in, the auth dependency
creates their user row and a funded account. So this script is a manual top-up for
local development, aimed at an account that already exists.

Sign up through the web app first, then run:

    uv run python -m seed --email you@example.com
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import Settings, get_settings
from db import SessionLocal
from models import Account, User
from services.sim.accounts import get_or_create_account


class SeedError(Exception):
    """The account could not be seeded. The message explains what to do about it."""


def seed_account(session: Session, email: str, settings: Settings) -> tuple[Account, bool]:
    """Ensure the user with this email has a funded account, and say if we just opened it."""
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        raise SeedError(
            f"No user with the email {email}. Sign up in the web app first, then run this again."
        )
    return get_or_create_account(session, user, starting_balance=settings.starting_balance)


def main() -> None:
    """Seed the account named on the command line and report what happened."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="the email you signed up with")
    args = parser.parse_args()

    settings = get_settings()
    with SessionLocal() as session:
        try:
            account, created = seed_account(session, args.email, settings)
        except SeedError as exc:
            sys.exit(str(exc))
        session.commit()

    opened = "opened" if created else "already open"
    print(f"Account {opened}: id={account.id}, cash={account.cash_balance}")


if __name__ == "__main__":
    main()
