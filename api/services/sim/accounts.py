"""Account provisioning: minting a funded paper-trading account.

Opening an account creates cash, so it belongs in the sim layer next to the rest of
the money-moving code. Both paths into the app come through here (a first sign-in
and the seed script), so an account is always funded the same way.

Like the rest of the sim, these functions flush but never commit: the caller owns
the transaction boundary.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Account, User


def get_or_create_account(
    session: Session, user: User, *, starting_balance: Decimal
) -> tuple[Account, bool]:
    """Return the user's account, opening a funded one if they don't have one yet.

    Returns the account and whether it was just created, so the caller knows
    whether there is anything to commit.
    """
    account = session.scalar(select(Account).where(Account.user_id == user.id))
    if account is not None:
        return account, False

    account = Account(
        user_id=user.id,
        cash_balance=starting_balance,
        starting_balance=starting_balance,
    )
    session.add(account)
    session.flush()  # assigns account.id
    return account, True
