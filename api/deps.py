"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from auth import get_current_user
from config import get_settings
from db import get_db
from models import Account, User
from services.sim.accounts import get_or_create_account


def get_current_account(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
) -> Account:
    """The signed-in user's account, opened and funded the first time they arrive.

    Every route scopes its queries to the account this returns, which is what keeps
    one user's money out of another's (Supabase RLS does not cover these tables:
    see auth.py).
    """
    account, created = get_or_create_account(
        session, user, starting_balance=get_settings().starting_balance
    )
    if created:
        # A first sign-in lands on a read-only route as often as not, and that route
        # will never commit. Persist the new user and their account here instead.
        session.commit()
    return account
