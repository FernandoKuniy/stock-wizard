"""Tests for the achievements feature: the pure predicates, the awarding layer, and the wiring.

The predicates decide who earned a badge, and a badge is a claim the app makes about how
someone invested, so the boundaries get tested hard: the exact day a hold tier flips, a
sell-and-rebuy resetting the clock, a dip that's a day or a percent short, and a dip on a
holding we couldn't price. The awarding layer is add-only and idempotent, and the two get
proven together with the account scoping every other route relies on.

The pure layer needs no clock (``as_of`` is passed in); the awarding layer takes an injectable
``now`` so "today" is pinned; the API tests backdate real transactions against the real clock.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from auth import get_token_verifier
from db import get_db
from main import app
from models import Account, Achievement, Transaction, User
from services.achievements import award_achievements
from services.analysis.achievements import (
    CATALOG,
    HOLD_TIERS,
    AccountFacts,
    Fill,
    PositionFact,
    continuous_hold_days,
    evaluate,
)
from services.market.candles import get_candle_client
from services.market.client import (
    CompanyProfile,
    MarketError,
    NewsItem,
    Quote,
    SymbolMatch,
    get_market_client,
)
from services.portfolio import HoldingView, PortfolioSnapshot

# A fixed "today" for the pure and awarding-layer tests, so day math never depends on when
# the suite runs.
AS_OF = date(2026, 7, 22)


def _days_ago(days: int) -> date:
    return AS_OF - timedelta(days=days)


# --- The pure hold-duration walk -----------------------------------------------------------


def test_hold_days_counts_from_the_buy() -> None:
    fills = [Fill(on=_days_ago(40), side="buy", quantity=Decimal(10))]
    assert continuous_hold_days(fills, AS_OF) == 40


def test_nothing_held_is_none() -> None:
    assert continuous_hold_days([], AS_OF) is None


def test_a_full_sell_breaks_the_hold() -> None:
    fills = [
        Fill(on=_days_ago(40), side="buy", quantity=Decimal(10)),
        Fill(on=_days_ago(5), side="sell", quantity=Decimal(10)),
    ]
    assert continuous_hold_days(fills, AS_OF) is None


def test_a_partial_sell_keeps_the_original_start() -> None:
    fills = [
        Fill(on=_days_ago(40), side="buy", quantity=Decimal(10)),
        Fill(on=_days_ago(5), side="sell", quantity=Decimal(4)),
    ]
    assert continuous_hold_days(fills, AS_OF) == 40


def test_adding_to_a_position_keeps_the_first_start() -> None:
    fills = [
        Fill(on=_days_ago(40), side="buy", quantity=Decimal(5)),
        Fill(on=_days_ago(10), side="buy", quantity=Decimal(5)),
    ]
    assert continuous_hold_days(fills, AS_OF) == 40


def test_selling_out_and_rebuying_resets_the_clock() -> None:
    fills = [
        Fill(on=_days_ago(200), side="buy", quantity=Decimal(10)),
        Fill(on=_days_ago(100), side="sell", quantity=Decimal(10)),
        Fill(on=_days_ago(30), side="buy", quantity=Decimal(4)),
    ]
    assert continuous_hold_days(fills, AS_OF) == 30


def test_same_day_buy_then_sell_is_not_held() -> None:
    day = _days_ago(40)
    fills = [
        Fill(on=day, side="buy", quantity=Decimal(10)),
        Fill(on=day, side="sell", quantity=Decimal(10)),
    ]
    assert continuous_hold_days(fills, AS_OF) is None


# --- The pure predicate ---------------------------------------------------------------------


def _position(symbol: str, *, held_days: int, loss: Decimal | None = None) -> PositionFact:
    return PositionFact(symbol=symbol, held_days=held_days, gain_loss_percent=loss)


def test_no_positions_earns_nothing() -> None:
    assert evaluate(AccountFacts(positions=())) == set()


def test_five_companies_needs_five() -> None:
    four = tuple(_position(f"S{i}", held_days=1) for i in range(4))
    assert "five_companies" not in evaluate(AccountFacts(positions=four))
    five = tuple(_position(f"S{i}", held_days=1) for i in range(5))
    assert "five_companies" in evaluate(AccountFacts(positions=five))


def test_hold_ladder_flips_at_each_threshold() -> None:
    assert evaluate(AccountFacts(positions=(_position("A", held_days=29),))) == set()
    assert evaluate(AccountFacts(positions=(_position("A", held_days=30),))) == {"held_one_month"}
    ninety = evaluate(AccountFacts(positions=(_position("A", held_days=90),)))
    assert ninety == {"held_one_month", "held_three_months"}
    a_year = evaluate(AccountFacts(positions=(_position("A", held_days=365),)))
    assert a_year == {
        "held_one_month",
        "held_three_months",
        "held_six_months",
        "held_one_year",
    }


def test_the_longest_hold_drives_the_ladder() -> None:
    # A brand-new position doesn't pull the ladder down: it's the longest hold that counts.
    positions = (_position("NEW", held_days=1), _position("OLD", held_days=200))
    earned = evaluate(AccountFacts(positions=positions))
    assert {"held_one_month", "held_three_months", "held_six_months"} <= earned
    assert "held_one_year" not in earned


def test_dip_needs_both_the_time_and_the_loss() -> None:
    # Held long enough and down enough: earned.
    down = (_position("A", held_days=40, loss=Decimal(-20)),)
    assert "held_through_a_dip" in evaluate(AccountFacts(positions=down))
    # Down enough but too new: not yet.
    fresh = (_position("A", held_days=29, loss=Decimal(-20)),)
    assert "held_through_a_dip" not in evaluate(AccountFacts(positions=fresh))
    # Held long enough but only a small dip: not a rough patch.
    shallow = (_position("A", held_days=40, loss=Decimal(-10)),)
    assert "held_through_a_dip" not in evaluate(AccountFacts(positions=shallow))
    # Exactly on the line counts.
    edge = (_position("A", held_days=40, loss=Decimal(-15)),)
    assert "held_through_a_dip" in evaluate(AccountFacts(positions=edge))


def test_dip_ignores_an_unpriced_holding() -> None:
    # A holding we couldn't price reads as unknown, never as a loss, so it can't trip the dip.
    unpriced = (_position("A", held_days=40, loss=None),)
    assert "held_through_a_dip" not in evaluate(AccountFacts(positions=unpriced))


def test_dip_fires_on_any_qualifying_position() -> None:
    positions = (
        _position("FINE", held_days=40, loss=Decimal(5)),
        _position("HURT", held_days=40, loss=Decimal(-30)),
    )
    assert "held_through_a_dip" in evaluate(AccountFacts(positions=positions))


def test_every_earnable_key_has_catalog_copy() -> None:
    # A maxed-out account earns every key; each one must be a real badge with copy, or the UI
    # would show a blank. This is the guard against the predicate and the catalog drifting.
    catalog_keys = {badge.key for badge in CATALOG}
    assert len(catalog_keys) == len(CATALOG)  # no duplicate keys
    maxed = evaluate(
        AccountFacts(
            positions=tuple(_position(f"S{i}", held_days=400, loss=Decimal(-50)) for i in range(5))
        )
    )
    assert maxed == catalog_keys
    assert {key for _, key in HOLD_TIERS} <= catalog_keys


# --- The awarding layer (add-only, idempotent) ---------------------------------------------


@pytest.fixture
def db(db_session: Session) -> Session:
    return db_session


def _account(session: Session) -> Account:
    user = User(email="learner@example.com", auth_id=uuid4())
    session.add(user)
    session.flush()
    account = Account(
        user_id=user.id, cash_balance=Decimal(100_000), starting_balance=Decimal(100_000)
    )
    session.add(account)
    session.flush()
    return account


def _buy(session: Session, account: Account, symbol: str, *, days_ago: int) -> None:
    txn = Transaction(
        account_id=account.id, symbol=symbol, side="buy", quantity=Decimal(1), price=Decimal(100)
    )
    txn.timestamp = datetime.combine(_days_ago(days_ago), time.min, tzinfo=UTC)
    session.add(txn)
    session.flush()


def _view(symbol: str, *, loss: Decimal | None = Decimal(0)) -> HoldingView:
    return HoldingView(
        symbol=symbol,
        quantity=Decimal(1),
        avg_cost=Decimal(100),
        cost_basis=Decimal(100),
        price=Decimal(100),
        market_value=Decimal(100),
        gain_loss=Decimal(0),
        gain_loss_percent=loss,
        weight=Decimal(100),
    )


def _snapshot(*views: HoldingView) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        cash=Decimal(0),
        starting_balance=Decimal(100_000),
        total_value=Decimal(100_000),
        total_cost_basis=Decimal(0),
        total_gain_loss=Decimal(0),
        total_gain_loss_percent=Decimal(0),
        cash_weight=Decimal(0),
        holdings=list(views),
        unpriced_symbols=[],
    )


def _now() -> datetime:
    return datetime.combine(AS_OF, time(12, 0), tzinfo=UTC)


def test_award_writes_a_newly_earned_badge(db: Session) -> None:
    account = _account(db)
    _buy(db, account, "AAPL", days_ago=400)

    result = award_achievements(db, account, _snapshot(_view("AAPL")), now=_now())

    assert "held_one_year" in result.newly_awarded
    rows = set(db.scalars(select(Achievement.key).where(Achievement.account_id == account.id)))
    assert "held_one_year" in rows


def test_award_is_idempotent(db: Session) -> None:
    account = _account(db)
    _buy(db, account, "AAPL", days_ago=400)
    snapshot = _snapshot(_view("AAPL"))

    first = award_achievements(db, account, snapshot, now=_now())
    second = award_achievements(db, account, snapshot, now=_now())

    assert first.newly_awarded  # earned on the first pass
    assert second.newly_awarded == []  # nothing new on the second
    keys = list(db.scalars(select(Achievement.key).where(Achievement.account_id == account.id)))
    assert len(keys) == len(set(keys))  # no duplicate rows


def test_a_badge_is_never_taken_back(db: Session) -> None:
    # Earn a badge, then award again with nothing held (what a reset leaves behind). The row
    # survives and the badge still reads as earned: it's a record, not a live status.
    account = _account(db)
    _buy(db, account, "AAPL", days_ago=400)
    award_achievements(db, account, _snapshot(_view("AAPL")), now=_now())

    db.execute(
        delete(Transaction)
        .where(Transaction.account_id == account.id)
        .execution_options(synchronize_session=False)
    )
    result = award_achievements(db, account, _snapshot(), now=_now())

    assert result.newly_awarded == []
    earned = {badge.key for badge in result.badges if badge.earned}
    assert "held_one_year" in earned


def test_award_reports_the_full_catalog(db: Session) -> None:
    account = _account(db)
    result = award_achievements(db, account, _snapshot(), now=_now())
    assert [badge.key for badge in result.badges] == [badge.key for badge in CATALOG]
    assert all(badge.earned is False for badge in result.badges)


def test_award_earns_the_dip_from_a_priced_loss(db: Session) -> None:
    account = _account(db)
    _buy(db, account, "AAPL", days_ago=40)
    result = award_achievements(
        db, account, _snapshot(_view("AAPL", loss=Decimal(-20))), now=_now()
    )
    assert "held_through_a_dip" in result.newly_awarded


# --- Through the API (wiring, scoping, reset) ----------------------------------------------

TOKEN_ALEX = "alex-token"
TOKEN_SAM = "sam-token"
CLAIMS = {
    TOKEN_ALEX: {"sub": str(uuid4()), "email": "alex@example.com"},
    TOKEN_SAM: {"sub": str(uuid4()), "email": "sam@example.com"},
}


class FakeVerifier:
    def verify(self, token: str) -> dict[str, Any]:
        try:
            return CLAIMS[token]
        except KeyError:
            raise HTTPException(status_code=401, detail="Sign in to continue.") from None


class FakeMarket:
    def __init__(self) -> None:
        self.prices = {"AAPL": 150.0, "MSFT": 300.0}

    def get_quote(self, symbol: str) -> Quote:
        price = self.prices[symbol.upper()]
        return Quote(symbol.upper(), price, 0.0, 0.0, price, price, price, price)

    def search(self, query: str) -> list[SymbolMatch]:
        return []

    def get_profile(self, symbol: str) -> CompanyProfile:
        return CompanyProfile(symbol.upper(), "Co", "NASDAQ", "Tech", "", 1e12, "A company.")

    def get_company_news(self, symbol: str) -> list[NewsItem]:
        return []


class FakeCandles:
    def get_candles(self, symbol: str, *, outputsize: int = 90) -> Any:
        raise MarketError("no candles in these tests")


@pytest.fixture
def market() -> FakeMarket:
    return FakeMarket()


@pytest.fixture
def overrides(db_session: Session, market: FakeMarket) -> Iterator[None]:
    def _db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_token_verifier] = lambda: FakeVerifier()
    app.dependency_overrides[get_market_client] = lambda: market
    app.dependency_overrides[get_candle_client] = lambda: FakeCandles()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client(overrides: None) -> TestClient:
    return TestClient(app, headers={"Authorization": f"Bearer {TOKEN_ALEX}"})


@pytest.fixture
def sams_client(overrides: None) -> TestClient:
    return TestClient(app, headers={"Authorization": f"Bearer {TOKEN_SAM}"})


def _earned_keys(payload: dict[str, Any]) -> set[str]:
    return {badge["key"] for badge in payload["achievements"] if badge["earned"]}


def _backdate_holding(db_session: Session, symbol: str, *, days_ago: int) -> None:
    """Push a just-bought transaction into the past so a hold-duration badge can be earned."""
    txn = db_session.scalars(select(Transaction).where(Transaction.symbol == symbol)).one()
    txn.timestamp = datetime.now(UTC) - timedelta(days=days_ago)
    db_session.commit()


def test_new_account_shows_every_badge_locked(client: TestClient) -> None:
    payload = client.get("/api/portfolio").json()
    keys = [badge["key"] for badge in payload["achievements"]]
    assert keys == [badge.key for badge in CATALOG]
    assert _earned_keys(payload) == set()


def test_holding_a_year_earns_the_ladder(client: TestClient, db_session: Session) -> None:
    client.post("/api/orders", json={"symbol": "AAPL", "side": "buy", "mode": "shares", "value": 1})
    _backdate_holding(db_session, "AAPL", days_ago=400)

    earned = _earned_keys(client.get("/api/portfolio").json())
    assert earned == {
        "held_one_month",
        "held_three_months",
        "held_six_months",
        "held_one_year",
    }


def test_badges_are_scoped_to_the_account(
    client: TestClient, sams_client: TestClient, db_session: Session
) -> None:
    client.post("/api/orders", json={"symbol": "AAPL", "side": "buy", "mode": "shares", "value": 1})
    _backdate_holding(db_session, "AAPL", days_ago=400)

    assert "held_one_year" in _earned_keys(client.get("/api/portfolio").json())
    # Sam did nothing, so Sam has earned nothing: one account's badges never leak into another.
    assert _earned_keys(sams_client.get("/api/portfolio").json()) == set()


def test_badges_survive_a_reset(client: TestClient, db_session: Session) -> None:
    client.post("/api/orders", json={"symbol": "AAPL", "side": "buy", "mode": "shares", "value": 1})
    _backdate_holding(db_session, "AAPL", days_ago=400)
    assert "held_one_year" in _earned_keys(client.get("/api/portfolio").json())

    client.post("/api/account/reset")

    after = client.get("/api/portfolio").json()
    assert after["holdings"] == []  # the money is wiped
    assert "held_one_year" in _earned_keys(after)  # the learning record isn't


def test_holding_through_a_loss_earns_the_dip_badge(
    client: TestClient, market: FakeMarket, db_session: Session
) -> None:
    client.post("/api/orders", json={"symbol": "AAPL", "side": "buy", "mode": "shares", "value": 1})
    _backdate_holding(db_session, "AAPL", days_ago=40)
    # The position is now down 20% against the $150 it was bought at.
    market.prices["AAPL"] = 120.0

    assert "held_through_a_dip" in _earned_keys(client.get("/api/portfolio").json())
