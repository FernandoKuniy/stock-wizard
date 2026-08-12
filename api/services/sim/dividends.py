"""Dividends: crediting an account for the stocks it held through a dividend's ex-date.

A dividend is cash a company pays you just for holding its stock. Like the limit-order sweep,
this runs lazily and with no background job: when the user loads their dashboard, ``sweep`` pays
any dividend whose ex-date has passed for shares the account held at the time, and records each
payment so it is never paid twice.

The rules, kept deliberately simple because this teaches a beginner:

- You are paid for shares you owned **before** the ex-date (a buy on the ex-date itself misses
  it, which is how real dividends work). Shares held then are reconstructed from the transaction
  ledger, the same source the performance history replays from.
- The cash is credited on settlement and the payment is recorded once, enforced by the unique
  (account, symbol, ex_date) constraint plus a skip of what's already on file, so running the
  sweep on every dashboard load is safe.
- We pay on the ex-date's held shares and credit at settlement (there is no separate pay-date in
  the model); for a teaching sim that keeps it to one date without changing the amount.

Like the rest of the sim, these functions flush but never commit: the caller owns the
transaction boundary (see ``routers`` for where the commit happens).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Account, DividendPayment, Transaction
from services.market.dividends import DividendEvent

_CASH = Decimal("0.0001")  # 4dp, matches the money columns
_ZERO = Decimal(0)


class DividendSource(Protocol):
    """The slice of the dividend provider the settlement needs: a symbol's dividends.

    References the market layer's ``DividendEvent`` directly, the same way ``engine.py``'s
    ``QuoteProvider`` references ``Quote``: the sim already depends on market types.
    """

    def get_dividends(self, symbol: str) -> list[DividendEvent]: ...


def sweep(
    session: Session,
    account: Account,
    provider: DividendSource,
    *,
    today: date | None = None,
) -> list[DividendPayment]:
    """Pay every unpaid dividend this account is owed, and return the payments made.

    Owed means: a dividend went ex on or before today, for a symbol the account held before
    that ex-date, and we haven't already paid it. Oldest first is irrelevant here, since each
    dividend is independent and nothing competes for cash.
    """
    on = today or datetime.now(UTC).date()
    transactions = list(
        session.scalars(
            select(Transaction)
            .where(Transaction.account_id == account.id)
            .order_by(Transaction.timestamp)
        )
    )
    if not transactions:
        return []

    already_paid = {
        (row.symbol, row.ex_date)
        for row in session.execute(
            select(DividendPayment.symbol, DividendPayment.ex_date).where(
                DividendPayment.account_id == account.id
            )
        )
    }

    paid: list[DividendPayment] = []
    for symbol in sorted({txn.symbol for txn in transactions}):
        for event in provider.get_dividends(symbol):
            if event.ex_date > on or (symbol, event.ex_date) in already_paid:
                continue
            shares = _shares_held_before(transactions, symbol, event.ex_date)
            if shares <= _ZERO:
                continue
            amount = (shares * event.amount).quantize(_CASH, rounding=ROUND_HALF_UP)
            if amount <= _ZERO:
                continue  # a sub-tenth-of-a-cent dividend rounds to nothing; don't record it
            account.cash_balance += amount
            payment = DividendPayment(
                account_id=account.id,
                symbol=symbol,
                ex_date=event.ex_date,
                per_share=event.amount,
                shares=shares,
                amount=amount,
            )
            session.add(payment)
            paid.append(payment)

    if paid:
        session.flush()
    return paid


def total_dividends(session: Session, account: Account) -> Decimal:
    """Every dividend dollar this account has ever been paid, summed exactly."""
    amounts = session.scalars(
        select(DividendPayment.amount).where(DividendPayment.account_id == account.id)
    )
    return sum(amounts, _ZERO)


def _shares_held_before(transactions: list[Transaction], symbol: str, ex_date: date) -> Decimal:
    """Net shares of ``symbol`` held going into ``ex_date``: buys before it, less sells before it.

    A trade on the ex-date itself doesn't count: to be paid you had to own the shares the day
    before the stock started trading without the dividend.
    """
    held = _ZERO
    for txn in transactions:
        if txn.symbol != symbol or txn.timestamp.date() >= ex_date:
            continue
        held += txn.quantity if txn.side == "buy" else -txn.quantity
    return held
