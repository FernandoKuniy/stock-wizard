"""End-to-end tests for the HTTP API.

The DB is the in-memory SQLite session from conftest, and the market and candle
clients are faked, so these exercise the real routes, sim, and analysis wiring
without touching Finnhub, Twelve Data, or Postgres.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from config import get_settings
from db import get_db
from deps import get_current_account
from main import app
from models import Account
from seed import seed_demo_account
from services.market.candles import CandlePoint, Candles, get_candle_client
from services.market.client import CompanyProfile, Quote, SymbolMatch, get_market_client


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
def account(db_session: Session) -> Account:
    acct = seed_demo_account(db_session, get_settings())
    db_session.commit()
    return acct


@pytest.fixture
def client(db_session: Session, account: Account) -> Iterator[TestClient]:
    def _db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_account] = lambda: account
    app.dependency_overrides[get_market_client] = lambda: FakeMarket()
    app.dependency_overrides[get_candle_client] = lambda: FakeCandles()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


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
