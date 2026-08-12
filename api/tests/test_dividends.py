"""Unit tests for dividends: the provider, the lazy settlement, and the history math.

The settlement moves real balances and must pay each dividend exactly once, so the coverage is
thorough: who is owed (shares held before the ex-date), rounding, idempotency, reset, account
isolation, and how the paid dividends fold into the performance line and the benchmark. No
network anywhere: the provider is a checked-in calendar and the tests build their own.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import get_settings
from models import Account, DividendPayment, Transaction, User
from services.analysis.history import (
    CashCredit,
    SharePayout,
    Trade,
    benchmark_series,
    never_sold_series,
    portfolio_value_series,
)
from services.market.dividends import DividendEvent, StaticDividendProvider
from services.sim.accounts import get_or_create_account
from services.sim.dividends import sweep, total_dividends
from services.sim.engine import reset


class FakeDividends:
    """A dividend source built from ``{symbol: [(ex_date, per_share), ...]}`` for one test."""

    def __init__(self, data: dict[str, list[tuple[date, str]]]) -> None:
        self._data = {
            symbol.upper(): [
                DividendEvent(symbol.upper(), ex, Decimal(amount)) for ex, amount in rows
            ]
            for symbol, rows in data.items()
        }

    def get_dividends(self, symbol: str) -> list[DividendEvent]:
        return list(self._data.get(symbol.upper(), []))


@pytest.fixture
def account(db_session: Session) -> Account:
    user = User(auth_id=uuid4(), email="holder@example.com")
    db_session.add(user)
    db_session.flush()
    acct, _ = get_or_create_account(
        db_session, user, starting_balance=get_settings().starting_balance
    )
    return acct


def buy_on(session: Session, account: Account, symbol: str, qty: str, on: date) -> None:
    """Record a buy transaction dated ``on`` (price is irrelevant to who is owed a dividend)."""
    _txn(session, account, symbol, "buy", qty, on)


def sell_on(session: Session, account: Account, symbol: str, qty: str, on: date) -> None:
    _txn(session, account, symbol, "sell", qty, on)


def _txn(session: Session, account: Account, symbol: str, side: str, qty: str, on: date) -> None:
    session.add(
        Transaction(
            account_id=account.id,
            symbol=symbol,
            side=side,
            quantity=Decimal(qty),
            price=Decimal("100"),
            timestamp=datetime.combine(on, time(20, 0), tzinfo=UTC),
        )
    )
    session.flush()


# --- the provider ------------------------------------------------------------------------


def test_provider_returns_events_sorted_by_ex_date() -> None:
    provider = StaticDividendProvider(
        {"KO": [("2024-06-14", "0.485"), ("2024-03-15", "0.485"), ("2024-09-13", "0.485")]}
    )

    events = provider.get_dividends("ko")

    assert [e.ex_date for e in events] == [
        date(2024, 3, 15),
        date(2024, 6, 14),
        date(2024, 9, 13),
    ]
    assert all(isinstance(e.amount, Decimal) for e in events)


def test_provider_has_no_dividends_for_an_unknown_symbol() -> None:
    # The truthful "none on record", never an error, so an off-list ticker just accrues nothing.
    assert StaticDividendProvider({}).get_dividends("ZZZZ") == []


def test_the_shipped_calendar_covers_the_demo_symbols() -> None:
    provider = StaticDividendProvider()
    for symbol in ("AAPL", "MSFT", "NVDA", "KO", "DIS", "SPY"):
        assert provider.get_dividends(symbol), f"expected dividends on record for {symbol}"


# --- settlement --------------------------------------------------------------------------


def test_pays_for_shares_held_before_the_ex_date(db_session: Session, account: Account) -> None:
    buy_on(db_session, account, "KO", "100", date(2026, 3, 1))
    provider = FakeDividends({"KO": [(date(2026, 3, 15), "0.51")]})

    paid = sweep(db_session, account, provider, today=date(2026, 3, 20))

    assert len(paid) == 1
    payment = paid[0]
    assert payment.symbol == "KO"
    assert payment.shares == Decimal("100")
    assert payment.per_share == Decimal("0.51")
    assert payment.amount == Decimal("51.0000")  # 100 * 0.51
    # The cash actually landed in the account.
    assert account.cash_balance == get_settings().starting_balance + Decimal("51.0000")


def test_a_buy_on_the_ex_date_itself_is_not_paid(db_session: Session, account: Account) -> None:
    # To be paid you had to own the shares *before* the stock traded without the dividend.
    buy_on(db_session, account, "KO", "100", date(2026, 3, 15))
    provider = FakeDividends({"KO": [(date(2026, 3, 15), "0.51")]})

    assert sweep(db_session, account, provider, today=date(2026, 3, 20)) == []
    assert account.cash_balance == get_settings().starting_balance


def test_selling_before_the_ex_date_forfeits_the_dividend(
    db_session: Session, account: Account
) -> None:
    buy_on(db_session, account, "KO", "100", date(2026, 3, 1))
    sell_on(db_session, account, "KO", "100", date(2026, 3, 10))
    provider = FakeDividends({"KO": [(date(2026, 3, 15), "0.51")]})

    assert sweep(db_session, account, provider, today=date(2026, 3, 20)) == []


def test_pays_only_the_shares_still_held_at_the_ex_date(
    db_session: Session, account: Account
) -> None:
    buy_on(db_session, account, "KO", "100", date(2026, 3, 1))
    sell_on(db_session, account, "KO", "60", date(2026, 3, 10))  # 40 left going into the ex-date
    provider = FakeDividends({"KO": [(date(2026, 3, 15), "0.50")]})

    paid = sweep(db_session, account, provider, today=date(2026, 3, 20))

    assert len(paid) == 1
    assert paid[0].shares == Decimal("40")
    assert paid[0].amount == Decimal("20.0000")  # 40 * 0.50


def test_a_future_ex_date_is_not_paid_yet(db_session: Session, account: Account) -> None:
    buy_on(db_session, account, "KO", "100", date(2026, 3, 1))
    provider = FakeDividends({"KO": [(date(2026, 6, 12), "0.51")]})

    assert sweep(db_session, account, provider, today=date(2026, 3, 20)) == []


def test_paying_is_idempotent_across_sweeps(db_session: Session, account: Account) -> None:
    buy_on(db_session, account, "KO", "100", date(2026, 3, 1))
    provider = FakeDividends({"KO": [(date(2026, 3, 15), "0.51")]})

    first = sweep(db_session, account, provider, today=date(2026, 3, 20))
    second = sweep(db_session, account, provider, today=date(2026, 3, 20))

    assert len(first) == 1
    assert second == []  # already paid; nothing new
    assert total_dividends(db_session, account) == Decimal("51.0000")
    assert account.cash_balance == get_settings().starting_balance + Decimal("51.0000")


def test_a_later_sweep_pays_a_newly_reached_dividend(db_session: Session, account: Account) -> None:
    buy_on(db_session, account, "KO", "100", date(2026, 3, 1))
    provider = FakeDividends({"KO": [(date(2026, 3, 15), "0.51"), (date(2026, 6, 12), "0.51")]})

    sweep(db_session, account, provider, today=date(2026, 3, 20))  # only the March one
    later = sweep(db_session, account, provider, today=date(2026, 6, 20))  # now June too

    assert len(later) == 1
    assert later[0].ex_date == date(2026, 6, 12)
    assert total_dividends(db_session, account) == Decimal("102.0000")


def test_a_sub_cent_dividend_rounds_to_nothing_and_is_not_recorded(
    db_session: Session, account: Account
) -> None:
    # 1 share of a $0.0001/share dividend is a hundredth of a cent: below what the money
    # columns can hold, so it pays nothing rather than recording a zero.
    buy_on(db_session, account, "NVDA", "1", date(2026, 3, 1))
    provider = FakeDividends({"NVDA": [(date(2026, 3, 5), "0.00001")]})

    assert sweep(db_session, account, provider, today=date(2026, 3, 20)) == []


def test_dividends_survive_nothing_but_a_reset_clears_them(
    db_session: Session, account: Account
) -> None:
    buy_on(db_session, account, "KO", "100", date(2026, 3, 1))
    provider = FakeDividends({"KO": [(date(2026, 3, 15), "0.51")]})
    sweep(db_session, account, provider, today=date(2026, 3, 20))
    assert total_dividends(db_session, account) == Decimal("51.0000")

    reset(db_session, account)

    assert total_dividends(db_session, account) == Decimal(0)
    assert db_session.scalars(select(DividendPayment)).all() == []
    assert account.cash_balance == account.starting_balance


def test_one_accounts_dividends_never_touch_another(db_session: Session) -> None:
    settings = get_settings()
    alex = User(auth_id=uuid4(), email="alex@example.com")
    sam = User(auth_id=uuid4(), email="sam@example.com")
    db_session.add_all([alex, sam])
    db_session.flush()
    alex_acct, _ = get_or_create_account(
        db_session, alex, starting_balance=settings.starting_balance
    )
    sam_acct, _ = get_or_create_account(db_session, sam, starting_balance=settings.starting_balance)
    buy_on(db_session, alex_acct, "KO", "100", date(2026, 3, 1))  # only Alex holds KO
    provider = FakeDividends({"KO": [(date(2026, 3, 15), "0.51")]})

    sweep(db_session, alex_acct, provider, today=date(2026, 3, 20))
    sweep(db_session, sam_acct, provider, today=date(2026, 3, 20))

    assert total_dividends(db_session, alex_acct) == Decimal("51.0000")
    assert total_dividends(db_session, sam_acct) == Decimal(0)
    assert sam_acct.cash_balance == settings.starting_balance


# --- folding into the performance history ------------------------------------------------

START = Decimal("100000")
DAYS = [date(2026, 3, 2), date(2026, 3, 3), date(2026, 3, 4), date(2026, 3, 5), date(2026, 3, 6)]


def test_a_dividend_lifts_the_portfolio_line_from_its_date(db_session: Session) -> None:
    # Hold cash only; a $50 dividend on day 3 lifts every point from then on.
    credits = [CashCredit(on=DAYS[2], amount=Decimal("50"))]

    series = portfolio_value_series(START, [], {}, DAYS, credits)

    assert [p.value for p in series] == [START, START, START + 50, START + 50, START + 50]


def test_the_index_dividend_lifts_the_benchmark_line_too(db_session: Session) -> None:
    # $100k into the index at $100 buys 1,000 shares. A $2/share payout on day 3 adds $2,000.
    closes = {day: Decimal("100") for day in DAYS}
    payouts = [SharePayout(on=DAYS[2], per_share=Decimal("2"))]

    series = benchmark_series(START, closes, DAYS, payouts)

    assert [p.value for p in series] == [
        START,
        START,
        START + 2000,
        START + 2000,
        START + 2000,
    ]


def test_an_index_dividend_on_the_first_day_is_not_counted() -> None:
    # The position is bought at the first day's open, so it misses a dividend going ex that day.
    closes = {day: Decimal("100") for day in DAYS}
    payouts = [SharePayout(on=DAYS[0], per_share=Decimal("2"))]

    series = benchmark_series(START, closes, DAYS, payouts)

    assert [p.value for p in series] == [START] * 5


def test_never_sold_difference_nets_out_the_dividends() -> None:
    # Buy 100 @ $100 on day 1, sell all @ $110 on day 3. Same $30 dividend applied to both the
    # real line and the never-sold line, so the difference is the price move alone.
    trades = [
        Trade("AAPL", "buy", Decimal("100"), Decimal("100"), DAYS[0]),
        Trade("AAPL", "sell", Decimal("100"), Decimal("110"), DAYS[2]),
    ]
    prices = {"AAPL": {day: Decimal("120") for day in DAYS}}
    credits = [CashCredit(on=DAYS[1], amount=Decimal("30"))]

    real = portfolio_value_series(START, trades, prices, DAYS, credits)
    held = never_sold_series(START, trades, prices, DAYS, credits)

    assert held is not None
    # The $30 dividend sits on both lines, so it cancels: the gap is only the price difference
    # between having sold at $110 and still holding at $120.
    difference = real[-1].value - held[-1].value
    assert difference == Decimal("100") * (Decimal("110") - Decimal("120"))
