"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from db import get_db
from models import Account


def get_current_account(session: Annotated[Session, Depends(get_db)]) -> Account:
    """Return the single seeded account (M1 has no auth yet)."""
    account = session.scalars(select(Account).order_by(Account.id)).first()
    if account is None:
        raise HTTPException(status_code=503, detail="No account yet. Run the seed script first.")
    return account
