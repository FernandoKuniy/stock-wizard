"""Unit tests for limit orders: resting, cancelling, and the lazy fill sweep.

The market is faked so no test touches Finnhub, and everything runs against the in-memory
SQLite session from conftest. Limit orders move real balances on a delay, which makes them
the easiest place in the app to get money wrong, so the coverage here is deliberately
thorough: both sides, the fill price, the guard rails when the money or the shares are gone
by the time the price arrives, and the account scoping.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import get_settings
from models import Account, Holding, Order, Transaction, User
from services.market.client import MarketError, Quote
from services.sim.accounts import get_or_create_account
from services.sim.engine import InsufficientShares, InvalidOrder, buy, sell
from services.sim.orders import CANCELLED, FILLED, OPEN, OrderNotFound, cancel, place, sweep


class FakeMarket:
    """A quote source with prices the test can move, and symbols it can make fail."""

    def __init__(self, prices: dict[str, float] | None = None) -> None:
        self.prices = dict(prices or {"AAPL": 100.0, "MSFT": 200.0})
        self.failing: set[str] = set()

    def get_quote(self, symbol: str) -> Quote:
        symbol = symbol.upper()
        if symbol in self.failing:
            raise MarketError(f"No quote available for {symbol}.")
        price = self.prices[symbol]
        return Quote(symbol, price, 0.0, 0.0, price, price, price, price)


def make_account(session: Session, email: str) -> Account:
    user = User(auth_id=uuid4(), email=email)
    session.add(user)
    session.flush()
    account, _ = get_or_create_account(
        session, user, starting_balance=get_settings().starting_balance
    )
    return account


@pytest.fixture
def market() -> FakeMarket:
    return FakeMarket()


@pytest.fixture
def account(db_session: Session) -> Account:
    return make_account(db_session, "learner@example.com")


@pytest.fixture
def other_account(db_session: Session) -> Account:
    return make_account(db_session, "someone-else@example.com")


def holding_for(session: Session, account: Account, symbol: str) -> Holding | None:
    return session.scalar(
        select(Holding).where(Holding.account_id == account.id, Holding.symbol == symbol)
    )


# --- placing -------------------------------------------------------------------------


def test_place_rests_an_order_without_moving_any_money(
    db_session: Session, account: Account
) -> None:
    before = account.cash_balance

    order = place(
        db_session, account, "aapl", side="buy", limit_price=Decimal("90"), quantity=Decimal("5")
    )

    assert order.status == OPEN
    assert order.symbol == "AAPL"  # stored uppercased
    assert order.quantity == Decimal("5")
    # Nothing is set aside: the cash only moves when it fills.
    assert account.cash_balance == before
    assert db_session.scalars(select(Transaction)).all() == []


def test_place_by_dollars_converts_at_the_limit_price(
    db_session: Session, account: Account
) -> None:
    order = place(
        db_session, account, "AAPL", side="buy", limit_price=Decimal("100"), amount=Decimal("500")
    )
    # At your limit, $500 buys exactly five shares.
    assert order.quantity == Decimal("5")


def test_place_rejects_a_limit_of_zero(db_session: Session, account: Account) -> None:
    with pytest.raises(InvalidOrder):
        place(
            db_session,
            account,
            "AAPL",
            side="buy",
            limit_price=Decimal("0"),
            quantity=Decimal("1"),
        )


def test_place_rejects_a_size_that_rounds_to_nothing(db_session: Session, account: Account) -> None:
    with pytest.raises(InvalidOrder):
        place(
            db_session,
            account,
            "AAPL",
            side="buy",
            limit_price=Decimal("100"),
            amount=Decimal("0.00001"),
        )


def test_place_rejects_selling_what_you_dont_own(db_session: Session, account: Account) -> None:
    # No shorting in this sim, so catch it now rather than letting it rest and auto-cancel.
    with pytest.raises(InsufficientShares):
        place(
            db_session,
            account,
            "AAPL",
            side="sell",
            limit_price=Decimal("120"),
            quantity=Decimal("1"),
        )


def test_place_rejects_selling_more_than_you_own(
    db_session: Session, account: Account, market: FakeMarket
) -> None:
    buy(db_session, account, "AAPL", quantity=Decimal("5"), market=market)

    with pytest.raises(InsufficientShares):
        place(
            db_session,
            account,
            "AAPL",
            side="sell",
            limit_price=Decimal("120"),
            quantity=Decimal("10"),
        )


# --- the sweep: filling --------------------------------------------------------------


def test_sweep_fills_a_buy_once_the_price_drops_to_the_limit(
    db_session: Session, account: Account, market: FakeMarket
) -> None:
    place(
        db_session, account, "AAPL", side="buy", limit_price=Decimal("90"), quantity=Decimal("10")
    )
    market.prices["AAPL"] = 90.0

    changed = sweep(db_session, account, market)

    assert [order.status for order in changed] == [FILLED]
    holding = holding_for(db_session, account, "AAPL")
    assert holding is not None
    assert holding.quantity == Decimal("10")


def test_sweep_leaves_a_buy_open_while_the_price_is_above_its_limit(
    db_session: Session, account: Account, market: FakeMarket
) -> None:
    order = place(
        db_session, account, "AAPL", side="buy", limit_price=Decimal("90"), quantity=Decimal("10")
    )
    market.prices["AAPL"] = 110.0

    assert sweep(db_session, account, market) == []
    assert order.status == OPEN
    assert holding_for(db_session, account, "AAPL") is None


def test_sweep_fills_at_the_limit_price_not_at_the_quote(
    db_session: Session, account: Account, market: FakeMarket
) -> None:
    before = account.cash_balance
    place(
        db_session, account, "AAPL", side="buy", limit_price=Decimal("100"), quantity=Decimal("10")
    )
    # We only look every so often, so by the time we notice, the price has run well past the
    # limit. The order would really have executed on the way through, at 100.
    market.prices["AAPL"] = 90.0

    sweep(db_session, account, market)

    txn = db_session.scalars(select(Transaction)).one()
    assert txn.price == Decimal("100")
    # 10 shares at the limit, not at the 90 we happened to see.
    assert account.cash_balance == before - Decimal("1000")
    holding = holding_for(db_session, account, "AAPL")
    assert holding is not None
    assert holding.avg_cost == Decimal("100")


def test_sweep_fills_a_sell_once_the_price_rises_to_the_limit(
    db_session: Session, account: Account, market: FakeMarket
) -> None:
    buy(db_session, account, "AAPL", quantity=Decimal("10"), market=market)  # 10 @ 100
    cash_after_buy = account.cash_balance
    place(
        db_session,
        account,
        "AAPL",
        side="sell",
        limit_price=Decimal("120"),
        quantity=Decimal("10"),
    )
    market.prices["AAPL"] = 130.0

    changed = sweep(db_session, account, market)

    assert [order.status for order in changed] == [FILLED]
    # Sold at the limit of 120, not the 130 we happened to see.
    assert account.cash_balance == cash_after_buy + Decimal("1200")
    assert holding_for(db_session, account, "AAPL") is None


def test_sweep_leaves_a_sell_open_while_the_price_is_below_its_limit(
    db_session: Session, account: Account, market: FakeMarket
) -> None:
    buy(db_session, account, "AAPL", quantity=Decimal("10"), market=market)
    order = place(
        db_session,
        account,
        "AAPL",
        side="sell",
        limit_price=Decimal("120"),
        quantity=Decimal("10"),
    )
    market.prices["AAPL"] = 110.0

    assert sweep(db_session, account, market) == []
    assert order.status == OPEN


def test_sweep_links_a_filled_order_to_its_trade(
    db_session: Session, account: Account, market: FakeMarket
) -> None:
    order = place(
        db_session, account, "AAPL", side="buy", limit_price=Decimal("100"), quantity=Decimal("2")
    )

    sweep(db_session, account, market)

    txn = db_session.scalars(select(Transaction)).one()
    assert order.transaction_id == txn.id
    assert order.resolved_at is not None
    # A limit fill is a normal trade, so it lands in the history like any other.
    assert txn.side == "buy"
    assert txn.quantity == Decimal("2")


# --- the sweep: guard rails ----------------------------------------------------------


def test_sweep_never_fills_a_symbol_it_cannot_price(
    db_session: Session, account: Account, market: FakeMarket
) -> None:
    order = place(
        db_session, account, "AAPL", side="buy", limit_price=Decimal("100"), quantity=Decimal("10")
    )
    market.failing.add("AAPL")

    # No price, no fill. We never execute on data we couldn't get.
    assert sweep(db_session, account, market) == []
    assert order.status == OPEN
    assert db_session.scalars(select(Transaction)).all() == []


def test_sweep_cancels_a_buy_the_account_can_no_longer_afford(
    db_session: Session, account: Account, market: FakeMarket
) -> None:
    order = place(
        db_session, account, "AAPL", side="buy", limit_price=Decimal("100"), quantity=Decimal("900")
    )
    # Spend most of the cash elsewhere while the order rests. Nothing was reserved for it.
    buy(db_session, account, "MSFT", amount=Decimal("60000"), market=market)
    cash_before_sweep = account.cash_balance

    sweep(db_session, account, market)

    assert order.status == CANCELLED
    assert order.cancel_reason is not None
    assert order.resolved_at is not None
    # Cancelled cleanly: no half-applied fill, no cash moved.
    assert account.cash_balance == cash_before_sweep
    assert holding_for(db_session, account, "AAPL") is None


def test_sweep_cancels_a_sell_when_the_shares_are_already_gone(
    db_session: Session, account: Account, market: FakeMarket
) -> None:
    buy(db_session, account, "AAPL", quantity=Decimal("10"), market=market)
    order = place(
        db_session,
        account,
        "AAPL",
        side="sell",
        limit_price=Decimal("120"),
        quantity=Decimal("10"),
    )
    # Sell the position at market before the limit ever triggers.
    sell(db_session, account, "AAPL", quantity=Decimal("10"), market=market)
    cash_before_sweep = account.cash_balance
    market.prices["AAPL"] = 130.0

    sweep(db_session, account, market)

    assert order.status == CANCELLED
    assert order.cancel_reason is not None
    assert account.cash_balance == cash_before_sweep


def test_sweep_fills_the_oldest_order_first_when_cash_is_tight(
    db_session: Session, account: Account, market: FakeMarket
) -> None:
    # Two orders that can't both be afforded: 600 shares at 100 is $60,000 each.
    first = place(
        db_session, account, "AAPL", side="buy", limit_price=Decimal("100"), quantity=Decimal("600")
    )
    second = place(
        db_session, account, "AAPL", side="buy", limit_price=Decimal("100"), quantity=Decimal("600")
    )

    sweep(db_session, account, market)

    # The one that waited longest gets the cash; the other is cancelled, not part-filled.
    assert first.status == FILLED
    assert second.status == CANCELLED
    holding = holding_for(db_session, account, "AAPL")
    assert holding is not None
    assert holding.quantity == Decimal("600")


# --- cancelling ----------------------------------------------------------------------


def test_cancel_closes_an_open_order(db_session: Session, account: Account) -> None:
    order = place(
        db_session, account, "AAPL", side="buy", limit_price=Decimal("90"), quantity=Decimal("1")
    )

    cancelled = cancel(db_session, account, order.id)

    assert cancelled.status == CANCELLED
    assert cancelled.resolved_at is not None
    # A user cancelling their own order needs no explanation; that field is for auto-cancels.
    assert cancelled.cancel_reason is None


def test_cancel_rejects_an_order_that_already_filled(
    db_session: Session, account: Account, market: FakeMarket
) -> None:
    order = place(
        db_session, account, "AAPL", side="buy", limit_price=Decimal("100"), quantity=Decimal("1")
    )
    sweep(db_session, account, market)

    with pytest.raises(InvalidOrder):
        cancel(db_session, account, order.id)


def test_cancel_rejects_an_unknown_order(db_session: Session, account: Account) -> None:
    with pytest.raises(OrderNotFound):
        cancel(db_session, account, 999)


# --- account scoping -----------------------------------------------------------------


def test_one_account_cannot_cancel_anothers_order(
    db_session: Session, account: Account, other_account: Account
) -> None:
    order = place(
        db_session, account, "AAPL", side="buy", limit_price=Decimal("90"), quantity=Decimal("1")
    )

    # Reaching for someone else's order looks exactly like reaching for one that isn't there.
    with pytest.raises(OrderNotFound):
        cancel(db_session, other_account, order.id)
    assert order.status == OPEN


def test_a_sweep_only_touches_its_own_accounts_orders(
    db_session: Session, account: Account, other_account: Account, market: FakeMarket
) -> None:
    order = place(
        db_session, account, "AAPL", side="buy", limit_price=Decimal("100"), quantity=Decimal("10")
    )

    # Someone else loading their dashboard must not fill this account's order.
    assert sweep(db_session, other_account, market) == []
    assert order.status == OPEN
    assert other_account.cash_balance == other_account.starting_balance
    assert db_session.scalars(select(Order).where(Order.account_id == other_account.id)).all() == []
