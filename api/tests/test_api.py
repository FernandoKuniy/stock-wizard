"""End-to-end tests for the HTTP API.

The DB is the in-memory SQLite session from conftest, and the market and candle
clients are faked, so these exercise the real routes, sim, and analysis wiring
without touching Finnhub, Twelve Data, or Postgres.

Auth runs for real too: requests carry a bearer token and go through the actual
``get_current_user`` -> ``get_current_account`` chain. Only the signature check is
faked (see test_auth.py for the real one), which lets these tests sign in as two
different people and prove their money stays separate.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import (
    get_demo_signup_code,
    get_demo_tutor_message_limit,
    get_signup_code,
    get_token_verifier,
)
from config import Settings
from db import get_db
from main import app
from models import Account, Transaction
from ratelimit import RateLimiter
from routers.account import get_seed_new_accounts
from routers.common import _round2
from routers.tutor import get_tutor_limiter
from seed import DEMO_BUYS
from services.market.candles import CandlePoint, Candles, get_candle_client
from services.market.client import (
    CompanyProfile,
    MarketError,
    NewsItem,
    Quote,
    SymbolMatch,
    get_market_client,
)
from services.market.dividends import StaticDividendProvider, get_dividend_provider
from services.tutor.provider import (
    Completion,
    TutorError,
    TutorProvider,
    get_tutor_provider,
)

# Two signed-in people, each with their own Supabase user id.
TOKEN_ALEX = "alex-token"
TOKEN_SAM = "sam-token"
CLAIMS = {
    TOKEN_ALEX: {"sub": str(uuid4()), "email": "alex@example.com"},
    TOKEN_SAM: {"sub": str(uuid4()), "email": "sam@example.com"},
}


class FakeVerifier:
    """Maps a test token to claims, standing in for the real JWKS signature check."""

    def verify(self, token: str) -> dict[str, Any]:
        try:
            return CLAIMS[token]
        except KeyError:
            raise HTTPException(status_code=401, detail="Sign in to continue.") from None


class FakeMarket:
    """A fake market client covering the methods the routes call."""

    def __init__(self, prices: dict[str, float] | None = None) -> None:
        self._prices = prices or {"AAPL": 150.0, "MSFT": 300.0}
        # Symbols whose quote should blow up, so tests can act out a flaky provider.
        self.failing: set[str] = set()
        # Profiles fail separately from quotes: the check-up's sector lookup degrades on its
        # own, and a test shouldn't have to break the price to break the sector.
        self.profiles_failing: set[str] = set()
        # Every profile lookup, so a test can prove we don't spend quota we don't need.
        self.profile_calls: list[str] = []
        # Today's percent change per symbol, for the big-move note. Flat unless a test says so.
        self.percent_changes: dict[str, float] = {}
        # The year-of-headlines archive, keyed by ISO date. Empty unless a test fills it, which
        # is the normal case: most days have no headline and the list must still work.
        self.archive: dict[str, list[NewsItem]] = {}
        self.archive_failing: set[str] = set()
        self.archive_calls: list[str] = []

    def get_quote(self, symbol: str) -> Quote:
        symbol = symbol.upper()
        if symbol in self.failing:
            raise MarketError(f"No quote available for {symbol}.")
        price = self._prices[symbol]
        change = self.percent_changes.get(symbol, 0.0)
        return Quote(symbol, price, 0.0, change, price, price, price, price)

    def search(self, query: str) -> list[SymbolMatch]:
        return [SymbolMatch("AAPL", "APPLE INC", "Common Stock")]

    def get_profile(self, symbol: str) -> CompanyProfile:
        symbol = symbol.upper()
        self.profile_calls.append(symbol)
        if symbol in self.profiles_failing:
            raise MarketError(f"No company profile available for {symbol}.")
        return CompanyProfile(
            symbol, "Apple Inc", "NASDAQ", "Technology", "", 2.9e12, "A tech company."
        )

    def get_news_by_day(self, symbol: str) -> dict[str, list[NewsItem]]:
        symbol = symbol.upper()
        self.archive_calls.append(symbol)
        if symbol in self.archive_failing:
            raise MarketError(f"No news available for {symbol}.")
        return self.archive

    def get_company_news(self, symbol: str) -> list[NewsItem]:
        symbol = symbol.upper()
        if symbol in self.failing:
            raise MarketError(f"No news available for {symbol}.")
        return [
            NewsItem(
                headline=f"{symbol} beats expectations",
                summary="A short summary of the day.",
                source="Reuters",
                url="https://example.com/1",
                date="2026-07-14",
            ),
            NewsItem(
                headline=f"Analysts weigh in on {symbol}",
                summary="Another summary.",
                source="Bloomberg",
                url="https://example.com/2",
                date="2026-07-13",
            ),
        ]


# Three trading days ending today, so the history spine has something to walk.
CHART_DAYS = [date.today() - timedelta(days=2), date.today() - timedelta(days=1), date.today()]
# The index climbs 10% over the window. Each symbol's last close matches its live quote,
# so today's point on the history chart lines up with today's portfolio total.
CHART_CLOSES = {
    "SPY": [500.0, 520.0, 550.0],
    "AAPL": [100.0, 120.0, 150.0],
    "MSFT": [280.0, 290.0, 300.0],
}


class FakeCandles:
    """Daily closes for the last three days, per symbol."""

    def __init__(self) -> None:
        self.failing: set[str] = set()

    def get_candles(self, symbol: str, *, outputsize: int = 90) -> Candles:
        symbol = symbol.upper()
        if symbol in self.failing:
            raise MarketError(f"No chart data available for {symbol}.")
        closes = CHART_CLOSES[symbol]
        points = [
            CandlePoint(day.isoformat(), close)
            for day, close in zip(CHART_DAYS, closes, strict=True)
        ]
        return Candles(symbol, points[-outputsize:])


class FakeTutor(TutorProvider):
    """A stand-in tutor that answers without a tool call, so the route can be tested end to end."""

    def complete(self, *, system: str, messages: object, tools: object) -> Completion:
        return Completion(text="Here's a look at your portfolio.", tool_calls=())


@pytest.fixture
def market() -> FakeMarket:
    return FakeMarket()


@pytest.fixture
def candles() -> FakeCandles:
    return FakeCandles()


@pytest.fixture
def overrides(db_session: Session, market: FakeMarket, candles: FakeCandles) -> Iterator[None]:
    """Point the app at the test session and the fake market, market data, and verifier."""

    def _db() -> Iterator[Session]:
        yield db_session

    # Lambdas, not the classes themselves: FastAPI would read a class's __init__
    # signature and start parsing its arguments as request parameters.
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_token_verifier] = lambda: FakeVerifier()
    app.dependency_overrides[get_market_client] = lambda: market
    app.dependency_overrides[get_candle_client] = lambda: candles
    # No dividends by default, so the money assertions elsewhere stay exact and don't shift when
    # the shipped calendar is refreshed. The dividend tests below opt in with their own data.
    app.dependency_overrides[get_dividend_provider] = lambda: StaticDividendProvider({})
    app.dependency_overrides[get_tutor_provider] = lambda: FakeTutor()
    # A permissive limiter by default, so the tutor tests aren't throttled; the throttle
    # test below swaps in a tiny one to exercise the limit itself.
    app.dependency_overrides[get_tutor_limiter] = lambda: RateLimiter(
        max_calls=10_000, per_seconds=60
    )
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client(overrides: None) -> TestClient:
    """Signed in as Alex."""
    return TestClient(app, headers={"Authorization": f"Bearer {TOKEN_ALEX}"})


@pytest.fixture
def sams_client(overrides: None) -> TestClient:
    """Signed in as Sam, a different user with their own account."""
    return TestClient(app, headers={"Authorization": f"Bearer {TOKEN_SAM}"})


@pytest.fixture
def anon_client(overrides: None) -> TestClient:
    """Not signed in at all."""
    return TestClient(app)


def open_account_on(db_session: Session, client: TestClient, opened_on: date) -> None:
    """Sign in (which opens the account), then backdate when it opened."""
    assert client.get("/api/portfolio").status_code == 200
    account = db_session.scalars(select(Account)).one()
    account.created_at = datetime.combine(opened_on, time.min)
    db_session.commit()


def test_health_needs_no_token(anon_client: TestClient) -> None:
    assert anon_client.get("/health").json() == {"status": "ok"}


def test_readiness_check_pings_the_database(anon_client: TestClient) -> None:
    # Open, like /health, and confirms the DB answers. It's what the keep-warm ping hits.
    resp = anon_client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready"}


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/portfolio"),
        ("get", "/api/transactions"),
        ("get", "/api/dividends"),
        ("post", "/api/account/reset"),
        ("post", "/api/orders"),
        ("post", "/api/tutor"),
        ("post", "/api/tutor/stream"),
        ("get", "/api/watchlist"),
        ("post", "/api/watchlist"),
        ("delete", "/api/watchlist/AAPL"),
        ("get", "/api/orders"),
        ("delete", "/api/orders/1"),
        ("post", "/api/recurring"),
        ("get", "/api/recurring"),
        ("patch", "/api/recurring/1"),
        ("delete", "/api/recurring/1"),
    ],
)
def test_account_routes_require_a_token(anon_client: TestClient, method: str, path: str) -> None:
    assert getattr(anon_client, method)(path).status_code == 401


def test_a_bad_token_is_rejected(overrides: None) -> None:
    impostor = TestClient(app, headers={"Authorization": "Bearer made-up"})
    assert impostor.get("/api/portfolio").status_code == 401


# --- dividends ---------------------------------------------------------------------------
# The settlement is unit-tested in test_dividends.py; these prove it's wired into the routes:
# paid when the dashboard loads, listed, paid once, and cleared by a reset.


def _arrange_dividend(client: TestClient, db_session: Session) -> None:
    """Buy 10 AAPL, backdate the buy, and put a $1/share AAPL dividend a few days in the past.

    A live buy is stamped "now", so it can never sit before an ex-date that's already passed;
    backdating it is how a test recreates an account that has held a stock across an ex-date.
    """
    assert client.get("/api/portfolio").status_code == 200  # opens the account
    client.post(
        "/api/orders",
        json={"symbol": "AAPL", "side": "buy", "mode": "shares", "value": 10, "type": "market"},
    )
    txn = db_session.scalars(select(Transaction)).one()
    txn.timestamp = datetime.combine(date.today() - timedelta(days=10), time.min)
    db_session.commit()
    ex_date = (date.today() - timedelta(days=5)).isoformat()
    app.dependency_overrides[get_dividend_provider] = lambda: StaticDividendProvider(
        {"AAPL": [(ex_date, "1.00")]}
    )


def test_dividends_are_paid_when_the_dashboard_loads_and_listed(
    client: TestClient, db_session: Session
) -> None:
    _arrange_dividend(client, db_session)

    portfolio = client.get("/api/portfolio").json()
    assert portfolio["dividend_income"] == 10.0  # 10 shares * $1.00
    assert portfolio["cash"] == 98510.0  # 100,000 - 1,500 for the shares + 10 dividend

    dividends = client.get("/api/dividends").json()
    assert len(dividends) == 1
    assert dividends[0]["symbol"] == "AAPL"
    assert dividends[0]["shares"] == 10.0
    assert dividends[0]["amount"] == 10.0


def test_a_dividend_is_paid_only_once(client: TestClient, db_session: Session) -> None:
    _arrange_dividend(client, db_session)

    first = client.get("/api/portfolio").json()
    second = client.get("/api/portfolio").json()

    assert first["dividend_income"] == 10.0
    assert second["dividend_income"] == 10.0  # not 20: settling twice pays once
    assert len(client.get("/api/dividends").json()) == 1


def test_a_reset_clears_dividends(client: TestClient, db_session: Session) -> None:
    _arrange_dividend(client, db_session)
    client.get("/api/portfolio")  # pays the dividend
    assert client.get("/api/dividends").json()  # non-empty

    after = client.post("/api/account/reset").json()

    assert after["dividend_income"] == 0.0
    assert client.get("/api/dividends").json() == []


# --- recurring investments ---------------------------------------------------------------
# The sweep is unit-tested in test_recurring.py; these prove it's wired into the routes: set up,
# fires on dashboard load, paused schedules stay put, and a reset clears them.


def test_a_recurring_buy_runs_when_the_dashboard_loads(
    client: TestClient, db_session: Session
) -> None:
    assert client.get("/api/portfolio").status_code == 200  # opens the account
    created = client.post(
        "/api/recurring", json={"symbol": "AAPL", "amount": 600, "cadence": "monthly"}
    )
    assert created.status_code == 200
    assert created.json()["active"] is True

    portfolio = client.get("/api/portfolio").json()
    holding = next((h for h in portfolio["holdings"] if h["symbol"] == "AAPL"), None)
    assert holding is not None
    assert holding["quantity"] == 4.0  # $600 at $150
    assert portfolio["cash"] == 99400.0  # 100,000 - 600

    # The next run is a month out, so loading again doesn't buy a second time.
    assert client.get("/api/portfolio").json()["cash"] == 99400.0


def test_recurring_can_be_paused_resumed_and_cancelled(client: TestClient) -> None:
    client.get("/api/portfolio")
    created = client.post(
        "/api/recurring", json={"symbol": "AAPL", "amount": 600, "cadence": "monthly"}
    ).json()
    sid = created["id"]

    paused = client.patch(f"/api/recurring/{sid}", json={"active": False}).json()
    assert paused["active"] is False
    # A paused schedule doesn't fire when the dashboard loads.
    assert client.get("/api/portfolio").json()["cash"] == 100000.0

    resumed = client.patch(f"/api/recurring/{sid}", json={"active": True}).json()
    assert resumed["active"] is True
    assert len(client.get("/api/recurring").json()) == 1

    assert client.delete(f"/api/recurring/{sid}").status_code == 204
    assert client.get("/api/recurring").json() == []


def test_recurring_rejects_a_symbol_it_cannot_price(client: TestClient, market: FakeMarket) -> None:
    client.get("/api/portfolio")
    market.failing.add("ZZZZ")
    resp = client.post(
        "/api/recurring", json={"symbol": "ZZZZ", "amount": 600, "cadence": "monthly"}
    )
    assert resp.status_code == 502


def test_a_reset_clears_recurring(client: TestClient) -> None:
    client.get("/api/portfolio")
    client.post("/api/recurring", json={"symbol": "AAPL", "amount": 600, "cadence": "monthly"})

    client.post("/api/account/reset")

    assert client.get("/api/recurring").json() == []


# --- returns breakdown -------------------------------------------------------------------
# The realized math is unit-tested in test_realized.py; this proves the split is on the payload
# and reconciles: realized + unrealized + dividends == total_gain_loss.


def test_realized_and_unrealized_reconcile_to_the_total(
    client: TestClient, market: FakeMarket
) -> None:
    client.get("/api/portfolio")  # opens the account
    client.post(
        "/api/orders",
        json={"symbol": "AAPL", "side": "buy", "mode": "shares", "value": 10, "type": "market"},
    )
    market._prices["AAPL"] = 200.0  # the price rises after the buy
    client.post(
        "/api/orders",
        json={"symbol": "AAPL", "side": "sell", "mode": "shares", "value": 4, "type": "market"},
    )

    p = client.get("/api/portfolio").json()
    assert p["realized_gain"] == 200.0  # 4 sold * (200 - 150)
    assert p["unrealized_gain"] == 300.0  # 6 held * (200 - 150)
    assert p["dividend_income"] == 0.0
    assert p["total_gain_loss"] == 500.0
    assert p["realized_gain"] + p["unrealized_gain"] + p["dividend_income"] == p["total_gain_loss"]


# --- the invite gate ---------------------------------------------------------------------
# By default (every test above) no code is configured, so accounts open on first sign-in.
# These turn the gate on and prove a signed-in user can't touch the app until they redeem.

INVITE_CODE = "s3cret-invite-code"


@pytest.fixture
def gated(overrides: None) -> str:
    """Turn the invite gate on for one test. ``overrides`` clears it again at teardown."""
    app.dependency_overrides[get_signup_code] = lambda: INVITE_CODE
    return INVITE_CODE


def _alex() -> TestClient:
    return TestClient(app, headers={"Authorization": f"Bearer {TOKEN_ALEX}"})


def test_gate_blocks_a_signed_in_but_uninvited_user(gated: str) -> None:
    resp = _alex().get("/api/portfolio")
    assert resp.status_code == 403
    # A machine-readable marker the frontend keys off to show the redeem screen. Distinct
    # from a 401, which would mean "your session ran out", not "you were never let in".
    assert resp.json()["detail"]["code"] == "invite_required"


def test_gate_covers_the_whole_app_not_just_account_routes(gated: str) -> None:
    # "Interact with the app" includes the routes that spend our quota and our tutor spend,
    # so a market-data call and a tutor call are gated too, not only the money routes.
    alex = _alex()
    assert alex.get("/api/quote/AAPL").status_code == 403
    assert (
        alex.post("/api/tutor", json={"messages": [{"role": "user", "content": "hi"}]}).status_code
        == 403
    )


def test_redeeming_the_right_code_opens_a_funded_account(gated: str) -> None:
    alex = _alex()
    assert alex.get("/api/portfolio").status_code == 403

    redeemed = alex.post("/api/redeem-invite", json={"code": gated})
    assert redeemed.status_code == 200
    assert redeemed.json() == {"status": "ok", "is_demo": False}

    portfolio = alex.get("/api/portfolio").json()
    assert portfolio["cash"] == 100000.0
    assert portfolio["starting_balance"] == 100000.0


def test_a_wrong_code_is_refused_and_stays_retryable(gated: str) -> None:
    alex = _alex()
    assert alex.post("/api/redeem-invite", json={"code": "not-it"}).status_code == 403
    # A typo doesn't lock anyone out: they're simply still uninvited and can try again.
    assert alex.get("/api/portfolio").status_code == 403
    assert alex.post("/api/redeem-invite", json={"code": gated}).status_code == 200
    assert alex.get("/api/portfolio").status_code == 200


def test_redeeming_twice_is_a_harmless_no_op(gated: str) -> None:
    alex = _alex()
    assert alex.post("/api/redeem-invite", json={"code": gated}).status_code == 200
    # Already in, so a second redeem (even a stale one with the wrong code) never locks
    # them back out. A double submit or a re-opened tab is safe.
    assert alex.post("/api/redeem-invite", json={"code": "stale"}).status_code == 200
    assert alex.get("/api/portfolio").status_code == 200


def test_redeeming_needs_a_token(gated: str) -> None:
    assert TestClient(app).post("/api/redeem-invite", json={"code": gated}).status_code == 401


# --- auto-seeding a new account with the demo sample -------------------------------------


class _FlatYearCandles:
    """A year of flat $100 bars for any symbol, so all five demo buys resolve in a test."""

    def get_candles(self, symbol: str, *, outputsize: int = 90) -> Candles:
        today = date.today()
        points = [
            CandlePoint((today - timedelta(days=offset)).isoformat(), 100.0)
            for offset in reversed(range(365))
        ]
        return Candles(symbol.upper(), points)


def _seeding_client() -> TestClient:
    """A client whose redeem seeds the demo sample, with a price for every demo symbol."""
    app.dependency_overrides[get_seed_new_accounts] = lambda: True
    app.dependency_overrides[get_candle_client] = lambda: _FlatYearCandles()
    app.dependency_overrides[get_market_client] = lambda: FakeMarket(
        prices={symbol: 100.0 for symbol, _, _ in DEMO_BUYS}
    )
    return TestClient(app, headers={"Authorization": f"Bearer {TOKEN_ALEX}"})


def test_a_plain_account_is_not_a_sample(client: TestClient) -> None:
    assert client.get("/api/portfolio").json()["is_sample"] is False


def test_redeem_seeds_the_sample_portfolio_when_enabled(overrides: None) -> None:
    alex = _seeding_client()
    assert alex.post("/api/redeem-invite", json={"code": "x"}).status_code == 200

    portfolio = alex.get("/api/portfolio").json()
    assert portfolio["is_sample"] is True
    assert len(portfolio["holdings"]) == len(DEMO_BUYS)


def test_reset_turns_the_sample_into_a_real_empty_account(overrides: None) -> None:
    alex = _seeding_client()
    alex.post("/api/redeem-invite", json={"code": "x"})
    assert alex.get("/api/portfolio").json()["is_sample"] is True

    # Reset is how a sample becomes their own: the flag clears and the holdings go.
    assert alex.post("/api/account/reset").status_code == 200
    portfolio = alex.get("/api/portfolio").json()
    assert portfolio["is_sample"] is False
    assert portfolio["holdings"] == []


def test_first_sign_in_opens_a_funded_account(client: TestClient) -> None:
    portfolio = client.get("/api/portfolio").json()

    assert portfolio["cash"] == 100000.0
    assert portfolio["starting_balance"] == 100000.0
    assert portfolio["holdings"] == []


def test_one_users_trades_never_touch_anothers(client: TestClient, sams_client: TestClient) -> None:
    client.post(
        "/api/orders", json={"symbol": "AAPL", "side": "buy", "mode": "shares", "value": 10}
    )

    mine = client.get("/api/portfolio").json()
    theirs = sams_client.get("/api/portfolio").json()

    assert mine["holdings"][0]["symbol"] == "AAPL"
    assert mine["cash"] == 98500.0
    # Sam sees their own untouched account, not Alex's shares or Alex's spent cash.
    assert theirs["holdings"] == []
    assert theirs["cash"] == 100000.0
    assert sams_client.get("/api/transactions").json() == []


def test_search(client: TestClient) -> None:
    body = client.get("/api/search", params={"q": "apple"}).json()
    assert body[0]["symbol"] == "AAPL"


def test_stock_has_quote_and_profile(client: TestClient) -> None:
    body = client.get("/api/stock/aapl").json()
    assert body["quote"]["price"] == 150.0
    assert body["profile"]["industry"] == "Technology"
    # Flat on the day, so there is nothing unusual to point at.
    assert body["big_move"] is None


def test_stock_points_at_a_big_day(client: TestClient, market: FakeMarket) -> None:
    market.percent_changes["AAPL"] = -7.2

    body = client.get("/api/stock/AAPL").json()

    assert body["big_move"] == "AAPL is down 7.2% today, which is a big day for one stock."
    # It says the move is unusual, never why. The headlines are a separate call and the
    # reader decides whether they explain anything.
    assert "because" not in body["big_move"].lower()


def test_candles(client: TestClient) -> None:
    points = client.get("/api/stock/AAPL/candles").json()["points"]
    assert [p["date"] for p in points] == [day.isoformat() for day in CHART_DAYS]
    assert [p["close"] for p in points] == CHART_CLOSES["AAPL"]


def test_biggest_moves_picks_out_the_days(client: TestClient) -> None:
    # AAPL ran 100 -> 120 -> 150 over the window, so both days were up and none were down.
    body = client.get("/api/stock/AAPL/moves").json()

    assert body["symbol"] == "AAPL"
    assert body["trading_days"] == 2
    # Biggest first, not newest first: 120 -> 150 is +25%, 100 -> 120 is +20%.
    assert [day["percent_change"] for day in body["up"]] == [25.0, 20.0]
    assert [day["date"] for day in body["up"]] == [
        CHART_DAYS[2].isoformat(),
        CHART_DAYS[1].isoformat(),
    ]
    assert body["down"] == []


def test_biggest_moves_attaches_a_headline_when_there_is_one(
    client: TestClient, market: FakeMarket
) -> None:
    market.archive = {
        CHART_DAYS[2].isoformat(): [
            NewsItem("AAPL jumps on earnings", "", "Reuters", "https://example.com/x", "")
        ]
    }

    body = client.get("/api/stock/AAPL/moves").json()

    on_the_day = next(day for day in body["up"] if day["date"] == CHART_DAYS[2].isoformat())
    assert on_the_day["news"][0]["headline"] == "AAPL jumps on earnings"
    # The other day had nothing, which is the normal case and not an error.
    other = next(day for day in body["up"] if day["date"] == CHART_DAYS[1].isoformat())
    assert other["news"] == []


def test_biggest_moves_still_works_when_the_news_archive_fails(
    client: TestClient, market: FakeMarket
) -> None:
    market.archive_failing.add("AAPL")

    body = client.get("/api/stock/AAPL/moves").json()

    # The moves are the point; the headlines are a bonus and never take the section down.
    assert body["trading_days"] == 2
    assert all(day["news"] == [] for day in body["up"])


def test_biggest_moves_refuses_without_price_history(
    client: TestClient, candles: FakeCandles
) -> None:
    candles.failing.add("AAPL")

    assert client.get("/api/stock/AAPL/moves").status_code == 502


def test_biggest_moves_needs_a_token(anon_client: TestClient) -> None:
    assert anon_client.get("/api/stock/AAPL/moves").status_code == 401


def test_what_if_answers_against_the_index(client: TestClient) -> None:
    # AAPL ran 100 -> 150 over the window (+50%), the index 500 -> 550 (+10%).
    body = client.get("/api/stock/AAPL/what-if", params={"amount": 1000, "period": "1m"}).json()

    assert body["amount"] == 1000.0
    assert body["stock"]["symbol"] == "AAPL"
    assert body["stock"]["buy_price"] == 100.0
    assert body["stock"]["value_now"] == 1500.0
    assert body["stock"]["gain_loss"] == 500.0
    assert body["stock"]["gain_loss_percent"] == 50.0

    # The comparison is the point: the same money in the index would be $1,100.
    assert body["benchmark"]["symbol"] == "SPY"
    assert body["benchmark"]["value_now"] == 1100.0
    assert body["difference"] == 400.0


def test_what_if_still_answers_without_the_index(client: TestClient, candles: FakeCandles) -> None:
    candles.failing.add("SPY")

    body = client.get("/api/stock/AAPL/what-if", params={"amount": 1000}).json()

    # Same asymmetry as the performance chart: no index costs only the comparison.
    assert body["stock"]["value_now"] == 1500.0
    assert body["benchmark"] is None
    assert body["difference"] is None


def test_what_if_needs_a_token(anon_client: TestClient) -> None:
    assert anon_client.get("/api/stock/AAPL/what-if").status_code == 401


def test_what_if_rejects_a_non_positive_amount(client: TestClient) -> None:
    assert client.get("/api/stock/AAPL/what-if", params={"amount": 0}).status_code == 422


def test_what_if_rejects_an_unknown_period(client: TestClient) -> None:
    assert client.get("/api/stock/AAPL/what-if", params={"period": "20y"}).status_code == 422


def test_what_if_says_so_when_the_history_is_unavailable(
    client: TestClient, candles: FakeCandles
) -> None:
    candles.failing.add("AAPL")
    assert client.get("/api/stock/AAPL/what-if").status_code == 502


def test_stock_news_returns_recent_articles(client: TestClient) -> None:
    body = client.get("/api/stock/AAPL/news").json()
    assert [item["headline"] for item in body] == [
        "AAPL beats expectations",
        "Analysts weigh in on AAPL",
    ]
    assert body[0]["source"] == "Reuters"
    assert body[0]["url"].startswith("https://")


def test_stock_news_needs_a_token(anon_client: TestClient) -> None:
    # News spends Finnhub quota, so it's for signed-in users only, like the other market routes.
    assert anon_client.get("/api/stock/AAPL/news").status_code == 401


def test_stock_news_degrades_when_unavailable(client: TestClient, market: FakeMarket) -> None:
    market.failing.add("AAPL")
    # A news outage is a 502; the stock page hides the section rather than breaking.
    assert client.get("/api/stock/AAPL/news").status_code == 502


def test_buy_updates_cash_and_portfolio(client: TestClient) -> None:
    order = client.post(
        "/api/orders", json={"symbol": "AAPL", "side": "buy", "mode": "shares", "value": 10}
    )
    assert order.status_code == 200, order.text
    assert order.json()["cash"] == 98500.0

    portfolio = client.get("/api/portfolio").json()
    assert portfolio["cash"] == 98500.0
    assert portfolio["total_value"] == 100000.0  # 98500 cash + 1500 at cost
    holding = portfolio["holdings"][0]
    assert holding["symbol"] == "AAPL"
    assert holding["quantity"] == 10.0
    assert holding["market_value"] == 1500.0
    assert holding["gain_loss"] == 0.0


def test_buy_by_dollars_buys_matching_shares(client: TestClient) -> None:
    client.post(
        "/api/orders", json={"symbol": "AAPL", "side": "buy", "mode": "dollars", "value": 300}
    )
    holding = client.get("/api/portfolio").json()["holdings"][0]
    assert holding["quantity"] == 2.0  # 300 / 150


def test_buy_insufficient_funds_returns_400(client: TestClient) -> None:
    order = client.post(
        "/api/orders", json={"symbol": "AAPL", "side": "buy", "mode": "shares", "value": 10000}
    )
    assert order.status_code == 400


def test_sell_reduces_holding(client: TestClient) -> None:
    client.post(
        "/api/orders", json={"symbol": "AAPL", "side": "buy", "mode": "shares", "value": 10}
    )
    order = client.post(
        "/api/orders", json={"symbol": "AAPL", "side": "sell", "mode": "shares", "value": 4}
    )
    assert order.status_code == 200
    holding = client.get("/api/portfolio").json()["holdings"][0]
    assert holding["quantity"] == 6.0


def test_transactions_history_newest_first(client: TestClient) -> None:
    client.post(
        "/api/orders", json={"symbol": "AAPL", "side": "buy", "mode": "shares", "value": 10}
    )
    client.post(
        "/api/orders", json={"symbol": "AAPL", "side": "sell", "mode": "shares", "value": 2}
    )
    txns = client.get("/api/transactions").json()
    assert len(txns) == 2
    assert txns[0]["side"] == "sell"  # newest first
    assert txns[1]["side"] == "buy"


def test_reset_clears_everything(client: TestClient) -> None:
    client.post(
        "/api/orders", json={"symbol": "AAPL", "side": "buy", "mode": "shares", "value": 10}
    )
    reset = client.post("/api/account/reset")
    assert reset.status_code == 200
    assert reset.json()["cash"] == 100000.0
    assert reset.json()["holdings"] == []
    assert client.get("/api/transactions").json() == []


def test_a_failed_quote_does_not_read_as_a_loss(client: TestClient, market: FakeMarket) -> None:
    client.post(
        "/api/orders", json={"symbol": "AAPL", "side": "buy", "mode": "shares", "value": 10}
    )
    # Finnhub goes flaky on AAPL right after the buy.
    market.failing.add("AAPL")

    portfolio = client.get("/api/portfolio").json()

    # The position is carried at what it cost, so the totals hold. Dropping it would have
    # shown a $1,500 loss the user never took.
    assert portfolio["unpriced_symbols"] == ["AAPL"]
    assert portfolio["total_value"] == 100000.0
    assert portfolio["total_gain_loss"] == 0.0
    # The row itself is honest about having no live price.
    assert portfolio["holdings"][0]["price"] is None


def test_history_draws_the_portfolio_against_the_index(
    client: TestClient, db_session: Session
) -> None:
    open_account_on(db_session, client, CHART_DAYS[0])
    client.post(
        "/api/orders", json={"symbol": "AAPL", "side": "buy", "mode": "shares", "value": 10}
    )

    body = client.get("/api/portfolio/history").json()

    assert body["benchmark_symbol"] == "SPY"
    assert [point["date"] for point in body["points"]] == [d.isoformat() for d in CHART_DAYS]

    # Both lines start at the starting balance, which is what makes the comparison fair.
    assert body["points"][0]["portfolio"] == 100000.0
    assert body["points"][0]["benchmark"] == 100000.0

    # The buy filled at the live quote (150) today, so 98,500 cash + 10 shares at today's
    # close of 150 = 100,000. Flat.
    comparison = body["comparison"]
    assert comparison["portfolio_value"] == 100000.0
    assert comparison["portfolio_percent"] == 0.0
    # The index went 500 -> 550, so the same $100k would have been $110,000.
    assert comparison["benchmark_value"] == 110000.0
    assert comparison["benchmark_percent"] == 10.0
    # Which means the index is $10,000 ahead. That is the lesson.
    assert comparison["difference"] == -10000.0


def test_portfolio_says_nothing_moved_on_an_empty_account(client: TestClient) -> None:
    assert client.get("/api/portfolio").json()["what_moved"] is None


def test_portfolio_names_what_moved(client: TestClient, market: FakeMarket) -> None:
    client.post(
        "/api/orders", json={"symbol": "AAPL", "side": "buy", "mode": "shares", "value": 10}
    )
    # Bought 10 shares at 150, now worth 170, so the position is up $200.
    market._prices["AAPL"] = 170.0

    what_moved = client.get("/api/portfolio").json()["what_moved"]

    assert what_moved == "AAPL is your only position that's moved, up $200.00."


def test_portfolio_leaves_an_unpriced_holding_out_of_the_story(
    client: TestClient, market: FakeMarket
) -> None:
    for symbol in ("AAPL", "MSFT"):
        client.post(
            "/api/orders", json={"symbol": symbol, "side": "buy", "mode": "shares", "value": 10}
        )
    market._prices["MSFT"] = 350.0  # up $500
    market.failing.add("AAPL")  # no quote, so we don't know how it's doing

    what_moved = client.get("/api/portfolio").json()["what_moved"]

    # AAPL is carried at cost in the totals, but "we couldn't price it" is not the same as
    # "it went nowhere", so it stays out of the sentence entirely.
    assert what_moved == "MSFT is your only position that's moved, up $500.00."


def test_checkup_of_an_empty_account_says_nothing(client: TestClient) -> None:
    # Nothing held, so there is no honest observation to make and no profile to look up.
    assert client.get("/api/portfolio/checkup").json() == []


def test_checkup_reads_the_account_it_is_given(client: TestClient) -> None:
    # Everything into one company: the biggest-position check should light up, and the
    # cash check should not, since it all got spent.
    client.post(
        "/api/orders", json={"symbol": "AAPL", "side": "buy", "mode": "dollars", "value": 90000}
    )

    found = {row["key"]: row for row in client.get("/api/portfolio/checkup").json()}

    assert found["one_big_position"]["status"] == "notable"
    assert "AAPL is 100% of what you own" in found["one_big_position"]["detail"]
    assert found["how_many_companies"]["status"] == "notable"
    assert found["cash_on_the_sidelines"]["status"] == "ok"


def test_checkup_flags_a_pile_of_cash(client: TestClient) -> None:
    # $1,500 of a $100,000 account invested, so almost all of it is still cash.
    client.post(
        "/api/orders", json={"symbol": "AAPL", "side": "buy", "mode": "dollars", "value": 1500}
    )

    found = {row["key"]: row for row in client.get("/api/portfolio/checkup").json()}

    assert found["cash_on_the_sidelines"]["status"] == "notable"
    assert "99% of your money is still sitting in cash" in found["cash_on_the_sidelines"]["detail"]


def test_checkup_flags_two_companies_in_the_same_industry(client: TestClient) -> None:
    # The fake market puts everything in Technology, so two holdings are one industry.
    for symbol in ("AAPL", "MSFT"):
        client.post(
            "/api/orders",
            json={"symbol": symbol, "side": "buy", "mode": "dollars", "value": 10000},
        )

    found = {row["key"]: row for row in client.get("/api/portfolio/checkup").json()}

    assert found["sector_spread"]["status"] == "notable"
    assert "one industry, Technology" in found["sector_spread"]["detail"]


def test_checkup_says_so_when_it_cannot_look_up_a_sector(
    client: TestClient, market: FakeMarket
) -> None:
    for symbol in ("AAPL", "MSFT"):
        client.post(
            "/api/orders",
            json={"symbol": symbol, "side": "buy", "mode": "dollars", "value": 10000},
        )
    market.profiles_failing.update({"AAPL", "MSFT"})

    found = {row["key"]: row for row in client.get("/api/portfolio/checkup").json()}

    # Not knowing is reported as not knowing, never guessed at, and the rest still works:
    # a failed profile lookup costs the sector check only, not the whole check-up.
    assert found["sector_spread"]["status"] == "unknown"
    assert found["how_many_companies"]["detail"] == "You own 2 companies."


def test_checkup_spends_no_profile_quota_on_a_single_holding(
    client: TestClient, market: FakeMarket
) -> None:
    client.post(
        "/api/orders", json={"symbol": "AAPL", "side": "buy", "mode": "dollars", "value": 10000}
    )
    market.profile_calls.clear()

    found = {row["key"]: row for row in client.get("/api/portfolio/checkup").json()}

    # One company is trivially all of one industry, so there is nothing to learn and no
    # reason to spend a call finding out.
    assert market.profile_calls == []
    assert "sector_spread" not in found


def test_checkup_is_scoped_to_the_signed_in_account(
    client: TestClient, sams_client: TestClient
) -> None:
    client.post(
        "/api/orders", json={"symbol": "AAPL", "side": "buy", "mode": "dollars", "value": 90000}
    )

    # Alex is all-in on one company; Sam has bought nothing and must not see Alex's position.
    assert sams_client.get("/api/portfolio/checkup").json() == []


def test_checkup_needs_a_token(anon_client: TestClient) -> None:
    assert anon_client.get("/api/portfolio/checkup").status_code == 401


def test_history_defaults_to_the_whole_account(client: TestClient, db_session: Session) -> None:
    open_account_on(db_session, client, CHART_DAYS[0])

    body = client.get("/api/portfolio/history").json()

    assert body["period"] == "all"
    # Over the whole life the baseline is the money the account opened with.
    assert body["baseline"] == 100000.0


def test_history_over_a_short_window_is_a_slice(client: TestClient, db_session: Session) -> None:
    open_account_on(db_session, client, CHART_DAYS[0])

    body = client.get("/api/portfolio/history?period=1m").json()

    # The fixture account is three days old, so a month is still its whole life, and the
    # baseline stays the starting balance rather than day one's closing value.
    assert body["period"] == "1m"
    assert body["baseline"] == 100000.0
    assert [point["date"] for point in body["points"]] == [d.isoformat() for d in CHART_DAYS]


def test_history_has_no_never_sold_before_you_sell(client: TestClient, db_session: Session) -> None:
    open_account_on(db_session, client, CHART_DAYS[0])
    client.post(
        "/api/orders", json={"symbol": "AAPL", "side": "buy", "mode": "shares", "value": 10}
    )

    # Never having sold, "what if you'd never sold" is just what happened.
    assert client.get("/api/portfolio/history").json()["never_sold"] is None


def test_history_compares_against_never_selling(client: TestClient, db_session: Session) -> None:
    open_account_on(db_session, client, CHART_DAYS[0])
    client.post(
        "/api/orders", json={"symbol": "AAPL", "side": "buy", "mode": "shares", "value": 10}
    )
    client.post(
        "/api/orders", json={"symbol": "AAPL", "side": "sell", "mode": "shares", "value": 10}
    )

    never_sold = client.get("/api/portfolio/history").json()["never_sold"]

    # Bought and sold at today's quote of 150, so the account is flat at 100,000 and holding
    # would have been worth the same. The point is that the comparison now exists.
    assert never_sold is not None
    assert never_sold["value"] == 100000.0
    assert never_sold["difference"] == 0.0


def test_never_sold_is_a_whole_life_question(client: TestClient, db_session: Session) -> None:
    open_account_on(db_session, client, CHART_DAYS[0])
    for side in ("buy", "sell"):
        client.post(
            "/api/orders", json={"symbol": "AAPL", "side": side, "mode": "shares", "value": 10}
        )

    # "What if you'd never sold" is about the whole account, so a narrowed window doesn't
    # answer it rather than answering a different question under the same name.
    assert client.get("/api/portfolio/history?period=1m").json()["never_sold"] is None
    assert client.get("/api/portfolio/history").json()["never_sold"] is not None


def test_history_rejects_a_period_we_do_not_serve(client: TestClient, db_session: Session) -> None:
    open_account_on(db_session, client, CHART_DAYS[0])

    # No 1D or 1W on purpose: a day-by-day view of your own money teaches trading on noise.
    assert client.get("/api/portfolio/history?period=1d").status_code == 422


def test_history_of_an_untouched_account_is_flat_cash(
    client: TestClient, db_session: Session
) -> None:
    open_account_on(db_session, client, CHART_DAYS[0])

    body = client.get("/api/portfolio/history").json()

    assert [point["portfolio"] for point in body["points"]] == [100000.0] * 3
    # Sitting in cash while the market climbed 10% is itself the teaching moment.
    assert body["comparison"]["difference"] == -10000.0


def test_history_still_draws_your_line_when_the_index_is_unavailable(
    client: TestClient, db_session: Session, candles: FakeCandles
) -> None:
    open_account_on(db_session, client, CHART_DAYS[0])
    client.post(
        "/api/orders", json={"symbol": "AAPL", "side": "buy", "mode": "shares", "value": 10}
    )
    candles.failing.add("SPY")

    body = client.get("/api/portfolio/history").json()

    # No index to compare against, but the user's own line is still correct.
    assert body["benchmark_symbol"] is None
    assert body["comparison"] is None
    assert [point["benchmark"] for point in body["points"]] == [None] * 3
    assert body["points"][-1]["portfolio"] == 100000.0


def test_history_refuses_to_draw_a_wrong_line(
    client: TestClient, db_session: Session, candles: FakeCandles
) -> None:
    open_account_on(db_session, client, CHART_DAYS[0])
    client.post(
        "/api/orders", json={"symbol": "AAPL", "side": "buy", "mode": "shares", "value": 10}
    )
    # Without AAPL's history we cannot value the position on any past day, and a chart
    # that silently leaves it out would understate the user's money.
    candles.failing.add("AAPL")

    response = client.get("/api/portfolio/history")

    assert response.status_code == 502
    assert "history" in response.json()["detail"].lower()


def test_tutor_answers_a_signed_in_user(client: TestClient) -> None:
    response = client.post(
        "/api/tutor", json={"messages": [{"role": "user", "content": "how am I doing?"}]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["reply"] == "Here's a look at your portfolio."


def test_tutor_streams_the_reply_over_sse(client: TestClient) -> None:
    response = client.post(
        "/api/tutor/stream", json={"messages": [{"role": "user", "content": "how am I doing?"}]}
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    # The default (non-chunking) FakeTutor sends the whole answer as one delta, then a done event.
    assert '"delta": "Here\'s a look at your portfolio."' in body
    assert '"done": true' in body


def test_tutor_stream_rejects_an_empty_conversation(client: TestClient) -> None:
    assert client.post("/api/tutor/stream", json={"messages": []}).status_code == 400


def test_tutor_stream_says_so_when_not_configured(client: TestClient) -> None:
    app.dependency_overrides[get_tutor_provider] = lambda: None
    body = {"messages": [{"role": "user", "content": "hi"}]}
    assert client.post("/api/tutor/stream", json=body).status_code == 503


def test_tutor_rejects_an_empty_conversation(client: TestClient) -> None:
    assert client.post("/api/tutor", json={"messages": []}).status_code == 400


def test_tutor_rejects_a_conversation_not_ending_with_the_user(client: TestClient) -> None:
    body = {"messages": [{"role": "assistant", "content": "hi"}]}
    assert client.post("/api/tutor", json=body).status_code == 400


def test_tutor_says_so_when_not_configured(client: TestClient) -> None:
    # No OpenAI key: the provider dependency resolves to None and the route degrades cleanly.
    app.dependency_overrides[get_tutor_provider] = lambda: None
    body = {"messages": [{"role": "user", "content": "hi"}]}
    assert client.post("/api/tutor", json=body).status_code == 503


def test_one_users_tutor_never_sees_anothers_money(
    client: TestClient, sams_client: TestClient
) -> None:
    # The tutor route builds its tools scoped to the signed-in account, the same guarantee
    # the tools themselves are unit-tested for. Both users reach their own tutor, never
    # each other's; the deeper scoping proof lives in test_tutor.py.
    client.post(
        "/api/orders", json={"symbol": "AAPL", "side": "buy", "mode": "shares", "value": 10}
    )
    body = {"messages": [{"role": "user", "content": "how am I doing?"}]}
    assert client.post("/api/tutor", json=body).status_code == 200
    assert sams_client.post("/api/tutor", json=body).status_code == 200


def test_the_tutor_is_throttled_per_account(overrides: None) -> None:
    # Two calls a minute here (a person never trips it; a runaway loop does). The third is
    # refused with 429, so the loop stops before it can run up the OpenAI bill.
    limiter = RateLimiter(max_calls=2, per_seconds=60)
    app.dependency_overrides[get_tutor_limiter] = lambda: limiter
    alex = TestClient(app, headers={"Authorization": f"Bearer {TOKEN_ALEX}"})
    body = {"messages": [{"role": "user", "content": "how am I doing?"}]}
    assert alex.post("/api/tutor", json=body).status_code == 200
    assert alex.post("/api/tutor", json=body).status_code == 200
    assert alex.post("/api/tutor", json=body).status_code == 429

    # The budget is per account, so one noisy user can't throttle everyone else.
    sam = TestClient(app, headers={"Authorization": f"Bearer {TOKEN_SAM}"})
    assert sam.post("/api/tutor", json=body).status_code == 200


def _limit(symbol: str, side: str, value: float, limit_price: float) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "side": side,
        "mode": "shares",
        "value": value,
        "type": "limit",
        "limit_price": limit_price,
    }


def test_a_limit_order_rests_without_moving_any_money(client: TestClient) -> None:
    # AAPL is 150, so a buy at 100 is still waiting.
    placed = client.post("/api/orders", json=_limit("AAPL", "buy", 10, 100))
    assert placed.status_code == 200, placed.text
    body = placed.json()

    # A limit order comes back as a resting order, not as a completed trade.
    assert body["transaction"] is None
    assert body["order"]["status"] == "open"
    assert body["order"]["limit_price"] == 100.0
    assert body["cash"] == 100000.0
    assert client.get("/api/portfolio").json()["holdings"] == []


def test_a_limit_order_needs_a_limit_price(client: TestClient) -> None:
    body = {"symbol": "AAPL", "side": "buy", "mode": "shares", "value": 1, "type": "limit"}
    assert client.post("/api/orders", json=body).status_code == 400


def test_loading_your_orders_fills_one_whose_price_arrived(client: TestClient) -> None:
    # AAPL is 150, so a buy limit at 200 has already been reached.
    client.post("/api/orders", json=_limit("AAPL", "buy", 10, 200))

    orders = client.get("/api/orders").json()

    assert orders[0]["status"] == "filled"
    # Filled at the limit, not at the 150 we happened to see.
    portfolio = client.get("/api/portfolio").json()
    assert portfolio["cash"] == 98000.0  # 10 shares at the 200 limit
    assert portfolio["holdings"][0]["avg_cost"] == 200.0


def test_loading_your_portfolio_fills_one_whose_price_arrived(client: TestClient) -> None:
    client.post("/api/orders", json=_limit("AAPL", "buy", 10, 200))

    # The dashboard is the other place orders get checked, since that's where people look.
    portfolio = client.get("/api/portfolio").json()

    assert portfolio["holdings"][0]["symbol"] == "AAPL"
    assert portfolio["holdings"][0]["quantity"] == 10.0


def test_cancelling_a_limit_order(client: TestClient) -> None:
    order = client.post("/api/orders", json=_limit("AAPL", "buy", 10, 100)).json()["order"]

    cancelled = client.delete(f"/api/orders/{order['id']}")

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    # Cancelling twice is an error, not a silent no-op.
    assert client.delete(f"/api/orders/{order['id']}").status_code == 400


def test_one_user_cannot_cancel_anothers_order(client: TestClient, sams_client: TestClient) -> None:
    order = client.post("/api/orders", json=_limit("AAPL", "buy", 10, 100)).json()["order"]

    # Someone else's order is indistinguishable from one that doesn't exist.
    assert sams_client.delete(f"/api/orders/{order['id']}").status_code == 404
    assert sams_client.get("/api/orders").json() == []
    assert client.get("/api/orders").json()[0]["status"] == "open"


def test_reset_clears_orders_including_filled_ones(client: TestClient) -> None:
    # One that fills (so it points at a transaction) and one still resting.
    client.post("/api/orders", json=_limit("AAPL", "buy", 10, 200))
    client.get("/api/portfolio")  # sweeps, filling the first
    client.post("/api/orders", json=_limit("MSFT", "buy", 1, 10))

    reset = client.post("/api/account/reset")

    # A filled order references the trade it became, so reset has to clear orders before
    # transactions or the foreign key would stop it.
    assert reset.status_code == 200, reset.text
    assert reset.json()["cash"] == 100000.0
    assert client.get("/api/orders").json() == []
    assert client.get("/api/transactions").json() == []


def test_watchlist_add_list_and_remove(client: TestClient) -> None:
    added = client.post("/api/watchlist", json={"symbol": "aapl"})
    assert added.status_code == 200, added.text
    # Stored uppercased, and the quote we validated with is handed straight back.
    assert added.json() == {"symbol": "AAPL", "price": 150.0, "percent_change": 0.0}

    assert client.get("/api/watchlist").json() == [
        {"symbol": "AAPL", "price": 150.0, "percent_change": 0.0}
    ]

    removed = client.delete("/api/watchlist/aapl")
    assert removed.status_code == 204
    assert client.get("/api/watchlist").json() == []


def test_watchlist_is_ordered_by_symbol(client: TestClient) -> None:
    client.post("/api/watchlist", json={"symbol": "MSFT"})
    client.post("/api/watchlist", json={"symbol": "AAPL"})
    symbols = [item["symbol"] for item in client.get("/api/watchlist").json()]
    assert symbols == ["AAPL", "MSFT"]


def test_watchlist_add_is_idempotent(client: TestClient) -> None:
    client.post("/api/watchlist", json={"symbol": "AAPL"})
    second = client.post("/api/watchlist", json={"symbol": "AAPL"})
    # Adding a symbol already on the list is fine, and doesn't duplicate it.
    assert second.status_code == 200
    assert [item["symbol"] for item in client.get("/api/watchlist").json()] == ["AAPL"]


def test_watchlist_rejects_a_symbol_with_no_quote(client: TestClient, market: FakeMarket) -> None:
    market.failing.add("ZZZZ")
    resp = client.post("/api/watchlist", json={"symbol": "ZZZZ"})
    assert resp.status_code == 502
    # A symbol that doesn't resolve is never stored, so it can't clutter the list.
    assert client.get("/api/watchlist").json() == []


def test_watchlist_degrades_when_a_quote_fails(client: TestClient, market: FakeMarket) -> None:
    client.post("/api/watchlist", json={"symbol": "AAPL"})
    # The quote goes flaky after AAPL is already on the list.
    market.failing.add("AAPL")
    # The symbol still shows up; only its price is null, just like a stale holding.
    assert client.get("/api/watchlist").json() == [
        {"symbol": "AAPL", "price": None, "percent_change": None}
    ]


def test_watchlist_can_skip_quotes_for_a_membership_check(client: TestClient) -> None:
    client.post("/api/watchlist", json={"symbol": "AAPL"})
    # The stock page's star only needs to know what's watched, without spending quote
    # quota on a ticker the user isn't actually looking at.
    assert client.get("/api/watchlist", params={"include_quotes": "false"}).json() == [
        {"symbol": "AAPL", "price": None, "percent_change": None}
    ]


def test_one_users_watchlist_never_touches_anothers(
    client: TestClient, sams_client: TestClient
) -> None:
    client.post("/api/watchlist", json={"symbol": "AAPL"})

    # Sam sees their own empty list, and removing AAPL from Sam's account can't reach
    # into Alex's.
    assert sams_client.get("/api/watchlist").json() == []
    assert sams_client.delete("/api/watchlist/AAPL").status_code == 204
    assert [item["symbol"] for item in client.get("/api/watchlist").json()] == ["AAPL"]


def test_round2_normalizes_negative_zero() -> None:
    # A sub-cent negative residual must not surface as -0.0 in the JSON.
    assert _round2(Decimal("-0.0001")) == 0.0
    assert str(_round2(Decimal("-0.0001"))) == "0.0"


# --- the demo tier -----------------------------------------------------------------------
# A second, publishable invite code opens a real account whose tutor has a small lifetime
# allowance. Everything else about the app is identical: only the route that costs us money
# per call is capped. These prove the cap holds where it has to and never bites a full user.

DEMO_CODE = "published-demo-code"


@pytest.fixture
def two_codes(overrides: None) -> None:
    """Turn the gate on with both a private code and a publishable demo one."""
    app.dependency_overrides[get_signup_code] = lambda: INVITE_CODE
    app.dependency_overrides[get_demo_signup_code] = lambda: DEMO_CODE
    app.dependency_overrides[get_demo_tutor_message_limit] = lambda: 1


def _ask(client: TestClient) -> int:
    body = {"messages": [{"role": "user", "content": "how am I doing?"}]}
    return int(client.post("/api/tutor", json=body).status_code)


def test_the_demo_code_opens_an_account_with_a_counted_allowance(two_codes: None) -> None:
    alex = _alex()
    assert alex.post("/api/redeem-invite", json={"code": DEMO_CODE}).status_code == 200

    me = alex.get("/api/me").json()
    assert me["is_demo"] is True
    assert me["tutor_messages_left"] == 1
    # The demo tier is only about the tutor: the money side of the app is untouched.
    assert alex.get("/api/portfolio").json()["cash"] == 100000.0


def test_the_private_code_still_opens_an_uncapped_account(two_codes: None) -> None:
    alex = _alex()
    assert alex.post("/api/redeem-invite", json={"code": INVITE_CODE}).status_code == 200

    me = alex.get("/api/me").json()
    assert me["is_demo"] is False
    # None, not a number: a full account has no allowance to count down.
    assert me["tutor_messages_left"] is None


def test_a_wrong_code_is_refused_even_with_two_configured(two_codes: None) -> None:
    assert _alex().post("/api/redeem-invite", json={"code": "not-it"}).status_code == 403


def test_a_demo_account_gets_its_question_then_the_banner_marker(two_codes: None) -> None:
    alex = _alex()
    alex.post("/api/redeem-invite", json={"code": DEMO_CODE})

    assert _ask(alex) == 200
    body = {"messages": [{"role": "user", "content": "and now?"}]}
    refused = alex.post("/api/tutor", json=body)
    assert refused.status_code == 403
    # The marker the frontend keys off to swap the composer for the "ask me for a code"
    # banner. Distinct from the 429 throttle, which means "slow down", not "you're done".
    assert refused.json()["detail"]["code"] == "demo_limit_reached"
    assert alex.get("/api/me").json()["tutor_messages_left"] == 0


def test_the_streaming_route_spends_the_same_allowance(two_codes: None) -> None:
    alex = _alex()
    alex.post("/api/redeem-invite", json={"code": DEMO_CODE})
    body = {"messages": [{"role": "user", "content": "how am I doing?"}]}

    # The UI streams, so the cap has to bind there too, not only on the plain route.
    assert alex.post("/api/tutor/stream", json=body).status_code == 200
    assert alex.post("/api/tutor/stream", json=body).status_code == 403
    assert alex.post("/api/tutor", json=body).status_code == 403


def test_a_full_account_is_never_capped(two_codes: None) -> None:
    alex = _alex()
    alex.post("/api/redeem-invite", json={"code": INVITE_CODE})
    for _ in range(5):
        assert _ask(alex) == 200
    assert alex.get("/api/me").json()["tutor_messages_left"] is None


def test_the_allowance_is_per_user(two_codes: None) -> None:
    alex, sam = _alex(), TestClient(app, headers={"Authorization": f"Bearer {TOKEN_SAM}"})
    alex.post("/api/redeem-invite", json={"code": DEMO_CODE})
    sam.post("/api/redeem-invite", json={"code": DEMO_CODE})

    assert _ask(alex) == 200
    assert _ask(alex) == 403
    # Alex spending theirs must not touch Sam's.
    assert _ask(sam) == 200


def test_a_reset_does_not_hand_out_a_fresh_question(two_codes: None) -> None:
    alex = _alex()
    alex.post("/api/redeem-invite", json={"code": DEMO_CODE})
    assert _ask(alex) == 200

    # The whole reason the counter lives on the user and not the account: resetting wipes
    # money, and if it wiped the allowance too the cap would be one click from useless.
    assert alex.post("/api/account/reset").status_code == 200
    assert _ask(alex) == 403


def test_an_unconfigured_tutor_does_not_cost_a_question(two_codes: None) -> None:
    alex = _alex()
    alex.post("/api/redeem-invite", json={"code": DEMO_CODE})
    app.dependency_overrides[get_tutor_provider] = lambda: None

    assert _ask(alex) == 503
    # Nothing was asked and nothing was spent, so the question is still there.
    assert alex.get("/api/me").json()["tutor_messages_left"] == 1
    app.dependency_overrides[get_tutor_provider] = lambda: FakeTutor()
    assert _ask(alex) == 200


def test_a_failed_tutor_call_refunds_the_question(two_codes: None) -> None:
    class BrokenTutor(TutorProvider):
        def complete(self, *, system: str, messages: object, tools: object) -> Completion:
            raise TutorError("the model is having a bad day")

    alex = _alex()
    alex.post("/api/redeem-invite", json={"code": DEMO_CODE})
    app.dependency_overrides[get_tutor_provider] = lambda: BrokenTutor()

    assert _ask(alex) == 502
    # Our fault, not theirs: an error that produced no answer gives the question back.
    assert alex.get("/api/me").json()["tutor_messages_left"] == 1
    app.dependency_overrides[get_tutor_provider] = lambda: FakeTutor()
    assert _ask(alex) == 200


def test_a_zero_limit_switches_the_demo_tutor_off(two_codes: None) -> None:
    # The kill switch: drop the allowance to zero and demo accounts lose the tutor without
    # anyone rotating the published code or shipping a deploy.
    app.dependency_overrides[get_demo_tutor_message_limit] = lambda: 0
    alex = _alex()
    alex.post("/api/redeem-invite", json={"code": DEMO_CODE})
    assert _ask(alex) == 403


def test_the_two_codes_must_differ() -> None:
    # A copy-paste that made them equal would quietly hand every holder of the published
    # code an unrestricted account, and nothing would look wrong until the bill arrived.
    with pytest.raises(ValidationError):
        Settings(
            finnhub_api_key="k",
            database_url="postgresql://u:p@localhost:5432/db",
            supabase_url="https://x.supabase.co",
            signup_code="same",
            demo_signup_code="same",
        )


def test_a_demo_user_can_trade_up_with_the_private_code(two_codes: None) -> None:
    alex = _alex()
    alex.post("/api/redeem-invite", json={"code": DEMO_CODE})
    assert _ask(alex) == 200
    assert _ask(alex) == 403

    # The point of the banner: they email for the private code and redeem it on the account
    # they already have. Without this the only way to lift a cap is editing the database.
    upgraded = alex.post("/api/redeem-invite", json={"code": INVITE_CODE})
    assert upgraded.status_code == 200
    assert upgraded.json()["is_demo"] is False
    assert alex.get("/api/me").json()["tutor_messages_left"] is None
    assert _ask(alex) == 200


def test_an_upgrade_only_ever_goes_upwards(two_codes: None) -> None:
    alex = _alex()
    alex.post("/api/redeem-invite", json={"code": INVITE_CODE})
    # A stale tab replaying the demo code must not take a full account back down.
    assert alex.post("/api/redeem-invite", json={"code": DEMO_CODE}).json()["is_demo"] is False
    assert _ask(alex) == 200


def test_a_wrong_code_on_an_existing_account_changes_nothing(two_codes: None) -> None:
    alex = _alex()
    alex.post("/api/redeem-invite", json={"code": DEMO_CODE})

    # Still forgiving: a typo here is a no-op, not a lockout. The response reports the tier
    # it left them on, which is how the banner knows the code didn't work.
    stale = alex.post("/api/redeem-invite", json={"code": "not-it"})
    assert stale.status_code == 200
    assert stale.json()["is_demo"] is True
