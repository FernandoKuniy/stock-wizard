"""Unit tests for the paper-trading sim: buys, sells, and reset.

The market is faked so no test touches Finnhub, and everything runs against the
in-memory SQLite session from conftest. This code moves real balances, so the
coverage is thorough: both order modes, averaging, the guard rails, and reset.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import get_settings
from models import Account, Holding, Transaction
from seed import seed_demo_account
from services.market.client import Quote
from services.sim.engine import (
    InsufficientFunds,
    InsufficientShares,
    InvalidOrder,
    buy,
    reset,
    sell,
)


class FakeMarket:
    """A stand-in quote source with fixed prices, so tests never hit the network."""

    def __init__(self, prices: dict[str, float]) -> None:
        self._prices = prices

    def get_quote(self, symbol: str) -> Quote:
        price = self._prices[symbol.upper()]
        return Quote(
            symbol=symbol.upper(),
            price=price,
            change=0.0,
            percent_change=0.0,
            high=price,
            low=price,
            open=price,
            previous_close=price,
        )


@pytest.fixture
def account(db_session: Session) -> Account:
    acct = seed_demo_account(db_session, get_settings())
    db_session.flush()
    return acct


def _holding(session: Session, account: Account, symbol: str) -> Holding | None:
    return session.scalar(
        select(Holding).where(Holding.account_id == account.id, Holding.symbol == symbol)
    )


def test_buy_by_shares_debits_cash_and_creates_holding(
    db_session: Session, account: Account
) -> None:
    txn = buy(db_session, account, "aapl", quantity=Decimal(10), market=FakeMarket({"AAPL": 150.0}))

    assert account.cash_balance == Decimal("98500")
    holding = _holding(db_session, account, "AAPL")
    assert holding is not None
    assert holding.quantity == Decimal(10)
    assert holding.avg_cost == Decimal(150)
    assert txn.side == "buy"
    assert txn.quantity == Decimal(10)
    assert txn.price == Decimal(150)


def test_buy_by_dollar_amount_buys_fractional_shares(db_session: Session, account: Account) -> None:
    buy(db_session, account, "AAPL", amount=Decimal(100), market=FakeMarket({"AAPL": 150.0}))

    holding = _holding(db_session, account, "AAPL")
    assert holding is not None
    assert holding.quantity == Decimal("0.666666")  # 100 / 150, rounded down to 6dp
    assert account.cash_balance == Decimal("99900.0001")  # spent 99.9999


def test_buy_averages_cost_across_lots(db_session: Session, account: Account) -> None:
    buy(db_session, account, "AAPL", quantity=Decimal(10), market=FakeMarket({"AAPL": 100.0}))
    buy(db_session, account, "AAPL", quantity=Decimal(10), market=FakeMarket({"AAPL": 200.0}))

    holding = _holding(db_session, account, "AAPL")
    assert holding is not None
    assert holding.quantity == Decimal(20)
    assert holding.avg_cost == Decimal(150)


def test_buy_rejects_insufficient_funds(db_session: Session, account: Account) -> None:
    with pytest.raises(InsufficientFunds):
        buy(db_session, account, "AAPL", quantity=Decimal(1000), market=FakeMarket({"AAPL": 200.0}))
    assert account.cash_balance == Decimal("100000")  # untouched


def test_buy_rejects_amount_too_small(db_session: Session, account: Account) -> None:
    with pytest.raises(InvalidOrder):
        buy(
            db_session,
            account,
            "AAPL",
            amount=Decimal("0.0001"),
            market=FakeMarket({"AAPL": 150.0}),
        )


@pytest.mark.parametrize(
    ("quantity", "amount"),
    [(None, None), (Decimal(1), Decimal(1)), (Decimal(0), None), (Decimal(-1), None)],
)
def test_buy_rejects_bad_order_input(
    db_session: Session,
    account: Account,
    quantity: Decimal | None,
    amount: Decimal | None,
) -> None:
    with pytest.raises(InvalidOrder):
        buy(
            db_session,
            account,
            "AAPL",
            quantity=quantity,
            amount=amount,
            market=FakeMarket({"AAPL": 150.0}),
        )


def test_sell_by_shares_credits_cash_and_reduces_holding(
    db_session: Session, account: Account
) -> None:
    buy(db_session, account, "AAPL", quantity=Decimal(10), market=FakeMarket({"AAPL": 150.0}))

    txn = sell(db_session, account, "AAPL", quantity=Decimal(4), market=FakeMarket({"AAPL": 160.0}))

    holding = _holding(db_session, account, "AAPL")
    assert holding is not None
    assert holding.quantity == Decimal(6)
    assert holding.avg_cost == Decimal(150)  # a sell does not change average cost
    # 100000 - 1500 (buy) + 640 (sell) = 99140
    assert account.cash_balance == Decimal("99140")
    assert txn.side == "sell"
    assert txn.quantity == Decimal(4)


def test_sell_all_removes_holding(db_session: Session, account: Account) -> None:
    buy(db_session, account, "AAPL", quantity=Decimal(10), market=FakeMarket({"AAPL": 150.0}))
    sell(db_session, account, "AAPL", quantity=Decimal(10), market=FakeMarket({"AAPL": 150.0}))

    assert _holding(db_session, account, "AAPL") is None
    assert account.cash_balance == Decimal("100000")


def test_sell_by_dollar_amount(db_session: Session, account: Account) -> None:
    buy(db_session, account, "AAPL", quantity=Decimal(10), market=FakeMarket({"AAPL": 150.0}))
    # Price now 200; selling $500 worth is 2.5 shares.
    sell(db_session, account, "AAPL", amount=Decimal(500), market=FakeMarket({"AAPL": 200.0}))

    holding = _holding(db_session, account, "AAPL")
    assert holding is not None
    assert holding.quantity == Decimal("7.5")


def test_sell_by_dollar_amount_caps_at_position(db_session: Session, account: Account) -> None:
    buy(db_session, account, "AAPL", quantity=Decimal(2), market=FakeMarket({"AAPL": 100.0}))
    # Ask for $500 but only own 2 shares worth 200: it sells all of them.
    sell(db_session, account, "AAPL", amount=Decimal(500), market=FakeMarket({"AAPL": 100.0}))

    assert _holding(db_session, account, "AAPL") is None


def test_sell_more_than_held_rejected(db_session: Session, account: Account) -> None:
    buy(db_session, account, "AAPL", quantity=Decimal(10), market=FakeMarket({"AAPL": 150.0}))
    with pytest.raises(InsufficientShares):
        sell(db_session, account, "AAPL", quantity=Decimal(11), market=FakeMarket({"AAPL": 150.0}))


def test_sell_nothing_held_rejected(db_session: Session, account: Account) -> None:
    with pytest.raises(InsufficientShares):
        sell(db_session, account, "AAPL", quantity=Decimal(1), market=FakeMarket({"AAPL": 150.0}))


def test_reset_restores_cash_and_clears_positions(db_session: Session, account: Account) -> None:
    buy(db_session, account, "AAPL", quantity=Decimal(10), market=FakeMarket({"AAPL": 150.0}))
    buy(db_session, account, "MSFT", quantity=Decimal(5), market=FakeMarket({"MSFT": 300.0}))

    reset(db_session, account)

    assert account.cash_balance == account.starting_balance
    assert db_session.scalars(select(Holding).where(Holding.account_id == account.id)).all() == []
    assert (
        db_session.scalars(select(Transaction).where(Transaction.account_id == account.id)).all()
        == []
    )
