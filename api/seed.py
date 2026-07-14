"""Fund a signed-up user's account, and optionally give it a history worth looking at.

Accounts open themselves: the first time someone signs in, the auth dependency creates
their user row and a funded account. So this script is a manual tool for local
development, aimed at an account that already exists.

Sign up through the web app first, then:

    uv run python -m seed --email you@example.com              # just make sure it's funded
    uv run python -m seed --email you@example.com --history    # ...and fill in demo trades

``--history`` backdates the account six months and buys five well-known companies at the
real closing price of the day it says it bought them. A brand new account has a portfolio
chart one day wide, which teaches nobody anything; this gives the S&P 500 comparison a
real curve to talk about from the first screen. The money is still fake and the prices
are still real, which is the whole premise of the app.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import Settings, get_settings
from db import SessionLocal
from models import Account, Transaction, User
from services.market.candles import FETCH_OUTPUTSIZE, Candles, get_candle_client
from services.market.client import MarketError
from services.sim.accounts import get_or_create_account
from services.sim.engine import backfill_buy


class CandleProvider(Protocol):
    """The slice of the candle client the seed needs: daily bars for a symbol."""

    def get_candles(self, symbol: str, *, outputsize: int = ...) -> Candles: ...


# What the demo account bought, how much of it, and how long ago. Spread across the window
# so the chart has something to show rather than one cliff. A mix on purpose: some of these
# will be up and some down by the time you read this, which is the honest lesson.
DEMO_BUYS = [
    ("AAPL", Decimal("20000"), 180),
    ("MSFT", Decimal("18000"), 150),
    ("NVDA", Decimal("15000"), 120),
    ("KO", Decimal("12000"), 90),
    ("DIS", Decimal("10000"), 60),
]
# Start the chart a little before the first buy, so you can see the line sitting in cash
# and then move. $75k of the $100k gets invested; the rest stays as cash.
LEAD_IN_DAYS = 7
_SHARES = Decimal("0.000001")  # 6dp, matching holdings.quantity
# US markets close at 4pm Eastern, which is 20:00 UTC.
MARKET_CLOSE = time(20, 0)


class SeedError(Exception):
    """The account could not be seeded. The message explains what to do about it."""


def seed_account(session: Session, email: str, settings: Settings) -> tuple[Account, bool]:
    """Ensure the user with this email has a funded account, and say if we just opened it.

    Only ever matches a user linked to Supabase Auth. Rows left over from before auth
    have no ``auth_id``, nobody can sign in as them, and they can share an email with a
    real user, so seeding one would pour money into an account no one will ever see.
    """
    user = session.scalar(
        select(User).where(User.email == email, User.auth_id.is_not(None)).order_by(User.id)
    )
    if user is None:
        raise SeedError(
            f"No signed-up user with the email {email}. "
            "Sign up in the web app first, then run this again."
        )
    return get_or_create_account(session, user, starting_balance=settings.starting_balance)


def seed_history(session: Session, account: Account, candles: CandleProvider) -> list[Transaction]:
    """Backdate the account and buy the demo holdings at real historical closing prices."""
    existing = session.scalar(
        select(Transaction).where(Transaction.account_id == account.id).limit(1)
    )
    if existing is not None:
        raise SeedError(
            "That account already has trades. Reset it in the app first if you want demo history."
        )

    today = datetime.now(UTC).date()
    fills = [
        (symbol, dollars, *_close_on_or_before(candles, symbol, today - timedelta(days=days_ago)))
        for symbol, dollars, days_ago in DEMO_BUYS
    ]

    # The account has to look older than its oldest trade, or the chart would start after
    # the money was already invested.
    earliest = min(day for _, _, day, _ in fills)
    account.created_at = _at_close(earliest - timedelta(days=LEAD_IN_DAYS))

    trades = []
    for symbol, dollars, day, price in sorted(fills, key=lambda fill: fill[2]):
        shares = (dollars / price).quantize(_SHARES, rounding=ROUND_DOWN)
        trades.append(
            backfill_buy(session, account, symbol, shares=shares, price=price, at=_at_close(day))
        )
    return trades


def _close_on_or_before(candles: CandleProvider, symbol: str, target: date) -> tuple[date, Decimal]:
    """The real closing price on ``target``, or on the last trading day before it."""
    try:
        series = candles.get_candles(symbol, outputsize=FETCH_OUTPUTSIZE)
    except MarketError as exc:
        raise SeedError(f"Couldn't load prices for {symbol}: {exc}") from exc

    for day, close in reversed(_days(series)):
        if day <= target:
            return day, close
    raise SeedError(f"No {symbol} price on or before {target}. Try a shorter history.")


def _days(series: Candles) -> list[tuple[date, Decimal]]:
    return [(date.fromisoformat(p.date), Decimal(str(p.close))) for p in series.points]


def _at_close(day: date) -> datetime:
    return datetime.combine(day, MARKET_CLOSE, tzinfo=UTC)


def main() -> None:
    """Seed the account named on the command line and report what happened."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="the email you signed up with")
    parser.add_argument(
        "--history",
        action="store_true",
        help="buy the demo holdings at real historical prices, so the charts have a curve",
    )
    args = parser.parse_args()

    settings = get_settings()
    with SessionLocal() as session:
        try:
            account, created = seed_account(session, args.email, settings)
            trades = seed_history(session, account, get_candle_client()) if args.history else []
        except SeedError as exc:
            sys.exit(str(exc))
        session.commit()

        opened = "opened" if created else "already open"
        print(f"Account {opened}: id={account.id}, cash={account.cash_balance}")
        for trade in trades:
            when = f"{trade.timestamp:%Y-%m-%d}"
            print(f"  {when}  bought {trade.quantity} {trade.symbol} at ${trade.price}")


if __name__ == "__main__":
    main()
