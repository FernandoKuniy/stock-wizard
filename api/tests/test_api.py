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
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from auth import get_token_verifier
from db import get_db
from main import _round2, app
from services.market.candles import CandlePoint, Candles, get_candle_client
from services.market.client import CompanyProfile, Quote, SymbolMatch, get_market_client

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

    def get_quote(self, symbol: str) -> Quote:
        price = self._prices[symbol.upper()]
        return Quote(symbol.upper(), price, 0.0, 0.0, price, price, price, price)

    def search(self, query: str) -> list[SymbolMatch]:
        return [SymbolMatch("AAPL", "APPLE INC", "Common Stock")]

    def get_profile(self, symbol: str) -> CompanyProfile:
        return CompanyProfile(
            symbol.upper(), "Apple Inc", "NASDAQ", "Technology", "", 2.9e12, "A tech company."
        )


class FakeCandles:
    def get_candles(self, symbol: str, *, outputsize: int = 90) -> Candles:
        points = [CandlePoint("2026-07-09", 1.0), CandlePoint("2026-07-10", 2.0)]
        return Candles(symbol.upper(), points)


@pytest.fixture
def overrides(db_session: Session) -> Iterator[None]:
    """Point the app at the test session and the fake market, market data, and verifier."""

    def _db() -> Iterator[Session]:
        yield db_session

    # Lambdas, not the classes themselves: FastAPI would read a class's __init__
    # signature and start parsing its arguments as request parameters.
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_token_verifier] = lambda: FakeVerifier()
    app.dependency_overrides[get_market_client] = lambda: FakeMarket()
    app.dependency_overrides[get_candle_client] = lambda: FakeCandles()
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


def test_health_needs_no_token(anon_client: TestClient) -> None:
    assert anon_client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/portfolio"),
        ("get", "/api/transactions"),
        ("post", "/api/account/reset"),
        ("post", "/api/orders"),
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
    assert [p["date"] for p in points] == ["2026-07-09", "2026-07-10"]


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


def test_round2_normalizes_negative_zero() -> None:
    # A sub-cent negative residual must not surface as -0.0 in the JSON.
    assert _round2(Decimal("-0.0001")) == 0.0
    assert str(_round2(Decimal("-0.0001"))) == "0.0"
