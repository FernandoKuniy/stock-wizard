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
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import get_token_verifier
from db import get_db
from main import _round2, app
from models import Account
from services.market.candles import CandlePoint, Candles, get_candle_client
from services.market.client import (
    CompanyProfile,
    MarketError,
    Quote,
    SymbolMatch,
    get_market_client,
)
from services.tutor.provider import Completion, TutorProvider, get_tutor_provider

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

    def get_quote(self, symbol: str) -> Quote:
        symbol = symbol.upper()
        if symbol in self.failing:
            raise MarketError(f"No quote available for {symbol}.")
        price = self._prices[symbol]
        return Quote(symbol, price, 0.0, 0.0, price, price, price, price)

    def search(self, query: str) -> list[SymbolMatch]:
        return [SymbolMatch("AAPL", "APPLE INC", "Common Stock")]

    def get_profile(self, symbol: str) -> CompanyProfile:
        return CompanyProfile(
            symbol.upper(), "Apple Inc", "NASDAQ", "Technology", "", 2.9e12, "A tech company."
        )


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
    app.dependency_overrides[get_tutor_provider] = lambda: FakeTutor()
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


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/portfolio"),
        ("get", "/api/transactions"),
        ("post", "/api/account/reset"),
        ("post", "/api/orders"),
        ("post", "/api/tutor"),
    ],
)
def test_account_routes_require_a_token(anon_client: TestClient, method: str, path: str) -> None:
    assert getattr(anon_client, method)(path).status_code == 401


def test_a_bad_token_is_rejected(overrides: None) -> None:
    impostor = TestClient(app, headers={"Authorization": "Bearer made-up"})
    assert impostor.get("/api/portfolio").status_code == 401


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


def test_candles(client: TestClient) -> None:
    points = client.get("/api/stock/AAPL/candles").json()["points"]
    assert [p["date"] for p in points] == [day.isoformat() for day in CHART_DAYS]
    assert [p["close"] for p in points] == CHART_CLOSES["AAPL"]


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


def test_round2_normalizes_negative_zero() -> None:
    # A sub-cent negative residual must not surface as -0.0 in the JSON.
    assert _round2(Decimal("-0.0001")) == 0.0
    assert str(_round2(Decimal("-0.0001"))) == "0.0"
