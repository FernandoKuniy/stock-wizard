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
    NewsItem,
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
        # Profiles fail separately from quotes: the check-up's sector lookup degrades on its
        # own, and a test shouldn't have to break the price to break the sector.
        self.profiles_failing: set[str] = set()
        # Every profile lookup, so a test can prove we don't spend quota we don't need.
        self.profile_calls: list[str] = []
        # Today's percent change per symbol, for the big-move note. Flat unless a test says so.
        self.percent_changes: dict[str, float] = {}

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
        ("get", "/api/watchlist"),
        ("post", "/api/watchlist"),
        ("delete", "/api/watchlist/AAPL"),
        ("get", "/api/orders"),
        ("delete", "/api/orders/1"),
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
