"""Account lifecycle routes: who am I, redeem an invite, and reset.

The redeem route is the one place account creation happens past the invite gate, so it depends
on the bare token identity rather than an account (which wouldn't exist yet). Reset returns the
portfolio payload, so it borrows the portfolio router's builder.
"""

from __future__ import annotations

import hmac
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from auth import (
    AuthIdentity,
    get_auth_identity,
    get_demo_signup_code,
    get_demo_tutor_message_limit,
    get_or_create_user,
    get_signup_code,
)
from config import get_settings
from models import User
from routers.common import AccountDep, CandleDep, DividendDep, MarketDep, SessionDep
from routers.portfolio import read_portfolio
from schemas import MeOut, PortfolioOut, RedeemInviteOut, RedeemInviteRequest
from seed import SeedError, seed_history
from services.sim.accounts import get_or_create_account
from services.sim.engine import SimError, reset

logger = logging.getLogger(__name__)

router = APIRouter()


def get_seed_new_accounts() -> bool:
    """Whether a fresh account gets the demo sample. A dependency so a test can flip it."""
    return get_settings().seed_new_accounts


@router.get("/api/me")
def read_me(
    identity: Annotated[AuthIdentity, Depends(get_auth_identity)],
    session: SessionDep,
    demo_limit: Annotated[int, Depends(get_demo_tutor_message_limit)],
) -> MeOut:
    """Who the caller is, and whether they've redeemed an invite code yet.

    Deliberately built on the bare token identity rather than ``get_current_account``, so it
    can answer for a signed-in user who hasn't been let past the gate (the only ones who need
    a different answer). The frontend uses it to show the redeem screen's bare header instead
    of the full app chrome.
    """
    user = session.scalar(select(User).where(User.auth_id == identity.auth_id))
    if user is None or not user.is_demo:
        return MeOut(email=identity.email, provisioned=user is not None)
    left = max(0, demo_limit - user.tutor_messages_used)
    return MeOut(email=identity.email, provisioned=True, is_demo=True, tutor_messages_left=left)


@router.post("/api/redeem-invite")
def redeem_invite(
    body: RedeemInviteRequest,
    identity: Annotated[AuthIdentity, Depends(get_auth_identity)],
    session: SessionDep,
    candles: CandleDep,
    signup_code: Annotated[str | None, Depends(get_signup_code)],
    demo_code: Annotated[str | None, Depends(get_demo_signup_code)],
    seed_sample: Annotated[bool, Depends(get_seed_new_accounts)],
) -> RedeemInviteOut:
    """Trade a valid invite code for a funded account, opening the door to the rest of the app.

    This is the one place account creation happens past the invite gate, so it deliberately
    depends on the bare token identity rather than ``get_current_account`` (which would 403 a
    user who hasn't redeemed yet, the very people who need this route).

    A user who already has an account is waved through: redeeming twice is a harmless no-op, so
    a double submit or a stale tab can never lock anyone out. Otherwise the code must match one
    of the two configured ones (see ``_match_code``): the private code opens a full account, and
    the publishable demo code opens one whose tutor has a small lifetime allowance. With no code
    configured the gate is off and any signed-in user is simply provisioned, full tier.

    When ``seed_new_accounts`` is on (the hosted demo), a fresh account is filled with the
    sample six-month portfolio so it teaches from the first screen. Seeding is best-effort: if
    the market data can't be fetched the account just opens empty, because opening it is the
    part that must not fail.
    """
    existing = session.scalar(select(User).where(User.auth_id == identity.auth_id))
    if existing is not None:
        return RedeemInviteOut()

    is_demo = _match_code(body.code.strip(), full=signup_code, demo=demo_code)

    user = get_or_create_user(session, auth_id=identity.auth_id, email=identity.email)
    user.is_demo = is_demo
    account, _ = get_or_create_account(
        session, user, starting_balance=get_settings().starting_balance
    )
    if seed_sample:
        try:
            seed_history(session, account, candles)
        except (SeedError, SimError) as exc:
            # A nice-to-have on top of the real account, so a data hiccup leaves it empty
            # rather than failing the signup outright.
            logger.warning("Could not seed a new account with sample history: %s", exc)
    session.commit()
    return RedeemInviteOut()


def _match_code(submitted: str, *, full: str | None, demo: str | None) -> bool:
    """Check a submitted invite code and report whether it was the demo one.

    Returns False for the full code (and for no gate at all, the local-development default),
    True for the publishable demo code, and raises 403 for anything else. Both comparisons are
    constant time, so the endpoint can't be used as a timing oracle to guess either code. A
    wrong code always runs both, so a near miss on one can't be told apart from a near miss on
    the other. The demo code only means anything when the gate is on: with no full code
    configured there is nothing to gate, and everyone is full tier.
    """
    if full is None:
        return False
    if hmac.compare_digest(submitted, full):
        return False
    if demo is not None and hmac.compare_digest(submitted, demo):
        return True
    raise HTTPException(
        status_code=403, detail="That invite code isn't right. Check it and try again."
    )


@router.post("/api/account/reset")
def reset_account(
    account: AccountDep, session: SessionDep, market: MarketDep, dividends: DividendDep
) -> PortfolioOut:
    """Wipe holdings, transactions, orders and dividend payments, and restore the starting cash."""
    reset(session, account)
    session.commit()
    return read_portfolio(account, session, market, dividends)
