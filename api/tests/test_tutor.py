"""Tutor tests: tools are account-scoped, numbers come from tools, and the loop holds.

The market and candle clients are faked and the DB is the in-memory SQLite session from
conftest, so these exercise the real tools, engine, guard, and provider translation without
touching OpenAI, Finnhub, Twelve Data, or Postgres. The one live check against the real model
is skipped unless ``OPENAI_API_KEY`` is set.
"""

from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from openai import OpenAIError
from sqlalchemy.orm import Session

from models import Account, User
from services.market.candles import CandlePoint, Candles
from services.market.client import CompanyProfile, MarketError, NewsItem, Quote
from services.sim.accounts import get_or_create_account
from services.sim.engine import buy
from services.tutor.engine import Turn, run_tutor
from services.tutor.guard import unaccounted_numbers
from services.tutor.provider import (
    Completion,
    OpenAIProvider,
    ToolCall,
    ToolSchema,
    TutorError,
    TutorProvider,
    UserMessage,
    get_tutor_provider,
)
from services.tutor.tools import Tool, build_tools

# Three trading days ending today; each symbol's last close matches its live quote so today's
# figures line up. Same shape as the history tests.
CHART_DAYS = [date.today() - timedelta(days=2), date.today() - timedelta(days=1), date.today()]
CHART_CLOSES = {
    "SPY": [500.0, 520.0, 550.0],
    "AAPL": [100.0, 120.0, 150.0],
    "MSFT": [280.0, 290.0, 300.0],
}
_NO_ARGS: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}


class FakeMarket:
    """Covers the market-client methods the tools call."""

    def __init__(self, prices: dict[str, float] | None = None) -> None:
        self._prices = prices or {"AAPL": 150.0, "MSFT": 300.0}
        self.failing: set[str] = set()

    def get_quote(self, symbol: str) -> Quote:
        symbol = symbol.upper()
        if symbol in self.failing:
            raise MarketError(f"No quote for {symbol}.")
        price = self._prices[symbol]
        return Quote(symbol, price, 0.0, 0.0, price, price, price, price)

    def get_profile(self, symbol: str) -> CompanyProfile:
        return CompanyProfile(
            symbol.upper(), "Apple Inc", "NASDAQ", "Technology", "", 2.9e12, "A tech company."
        )

    def get_company_news(self, symbol: str) -> list[NewsItem]:
        return [
            NewsItem(
                "Apple climbs after earnings", "Shares rose.", "Reuters", "2024-01-02", "http://x"
            )
        ]


class FakeCandles:
    """Daily closes per symbol over the three chart days."""

    def get_candles(self, symbol: str, *, outputsize: int = 90) -> Candles:
        symbol = symbol.upper()
        if symbol not in CHART_CLOSES:
            raise MarketError(f"No chart data for {symbol}.")
        points = [
            CandlePoint(day.isoformat(), close)
            for day, close in zip(CHART_DAYS, CHART_CLOSES[symbol], strict=True)
        ]
        return Candles(symbol, points[-outputsize:])


class Scripted(TutorProvider):
    """A stand-in model that returns pre-scripted turns, ignoring the messages it's handed."""

    def __init__(self, completions: list[Completion]) -> None:
        self._completions = list(completions)

    def complete(self, *, system: str, messages: Any, tools: Any) -> Completion:
        return self._completions.pop(0)


def _account(session: Session, email: str) -> Account:
    user = User(auth_id=uuid4(), email=email)
    session.add(user)
    session.flush()
    account, _ = get_or_create_account(session, user, starting_balance=Decimal(100000))
    account.created_at = datetime.combine(CHART_DAYS[0], time.min)
    session.flush()
    return account


def _account_holding_aapl(session: Session, market: FakeMarket) -> Account:
    account = _account(session, "alex@example.com")
    txn = buy(session, account, "AAPL", quantity=Decimal(10), market=market)
    txn.timestamp = datetime.combine(CHART_DAYS[-1], time.min)  # filled today
    session.flush()
    return account


def _by_name(tools: list[Tool]) -> dict[str, Tool]:
    return {tool.schema.name: tool for tool in tools}


def _tool(
    session: Session, account: Account, market: FakeMarket, candles: FakeCandles, name: str
) -> Tool:
    return _by_name(build_tools(session, account, market, candles))[name]


# --- Tools: account scoping and code-computed figures ---------------------------------------


def test_portfolio_summary_is_scoped_to_the_account(db_session: Session) -> None:
    market, candles = FakeMarket(), FakeCandles()
    alex = _account_holding_aapl(db_session, market)
    sam = _account(db_session, "sam@example.com")

    alex_summary = _tool(db_session, alex, market, candles, "get_portfolio_summary").run({})
    sam_summary = _tool(db_session, sam, market, candles, "get_portfolio_summary").run({})

    assert alex_summary["holdings"][0]["symbol"] == "AAPL"
    assert alex_summary["cash"] == 98500.0
    # Sam sees only their own untouched account, never Alex's shares or spent cash.
    assert sam_summary["holdings"] == []
    assert sam_summary["cash"] == 100000.0


def test_position_detail_reports_code_figures_and_volatility(db_session: Session) -> None:
    market, candles = FakeMarket(), FakeCandles()
    account = _account_holding_aapl(db_session, market)
    tool = _tool(db_session, account, market, candles, "get_position_detail")

    detail = tool.run({"symbol": "aapl"})
    assert detail["shares"] == 10.0
    assert detail["price"] == 150.0
    assert detail["market_value"] == 1500.0
    assert detail["gain_loss"] == 0.0  # bought at 150, priced at 150
    assert detail["annualized_volatility_percent"] > 0

    assert "error" in tool.run({"symbol": "MSFT"})  # not held


def test_concentration_of_a_single_holding(db_session: Session) -> None:
    market, candles = FakeMarket(), FakeCandles()
    account = _account_holding_aapl(db_session, market)
    result = _tool(db_session, account, market, candles, "get_concentration").run({})

    assert result["position_count"] == 1
    assert result["biggest_position"] == "AAPL"
    assert result["biggest_position_weight_percent"] == 100.0  # of the holdings
    assert result["sector_weights_percent"] == {"Technology": 100.0}


def test_benchmark_comparison_matches_the_history_math(db_session: Session) -> None:
    market, candles = FakeMarket(), FakeCandles()
    account = _account_holding_aapl(db_session, market)
    result = _tool(db_session, account, market, candles, "get_benchmark_comparison").run({})

    # 98,500 cash + 10 AAPL at 150 = 100,000, flat. The index went 500 -> 550, so the same
    # money would have been 110,000. The index is $10,000 ahead.
    assert result["your_value"] == 100000.0
    assert result["your_return_percent"] == 0.0
    assert result["benchmark_value"] == 110000.0
    assert result["benchmark_return_percent"] == 10.0
    assert result["difference"] == -10000.0


def test_recent_news_returns_headlines(db_session: Session) -> None:
    market, candles = FakeMarket(), FakeCandles()
    account = _account(db_session, "alex@example.com")
    result = _tool(db_session, account, market, candles, "get_recent_news").run({"symbol": "AAPL"})
    assert result["articles"][0]["headline"] == "Apple climbs after earnings"


def test_explain_term_uses_the_glossary(db_session: Session) -> None:
    market, candles = FakeMarket(), FakeCandles()
    account = _account(db_session, "alex@example.com")
    explain = _tool(db_session, account, market, candles, "explain_term")
    assert "paid" in explain.run({"term": "cost basis"})["definition"].lower()
    assert explain.run({"term": "florps"})["known"] is False


# --- Engine: the tool-calling loop ----------------------------------------------------------


def test_engine_runs_a_tool_then_narrates_its_figures(db_session: Session) -> None:
    market, candles = FakeMarket(), FakeCandles()
    account = _account_holding_aapl(db_session, market)
    tools = build_tools(db_session, account, market, candles)
    provider = Scripted(
        [
            Completion(text="", tool_calls=(ToolCall("c1", "get_portfolio_summary", {}),)),
            Completion(text="You've got $98,500 in cash right now.", tool_calls=()),
        ]
    )

    answer = run_tutor(provider, tools, [Turn("user", "how am I doing?")])

    assert "98,500" in answer.reply
    # The figure it quoted came from the tool, so the provenance guard is clean.
    assert unaccounted_numbers(answer.reply, [tools[0].run({})]) == []


def test_engine_survives_an_unknown_tool_name(db_session: Session) -> None:
    market, candles = FakeMarket(), FakeCandles()
    account = _account(db_session, "alex@example.com")
    tools = build_tools(db_session, account, market, candles)
    provider = Scripted(
        [
            Completion(text="", tool_calls=(ToolCall("c1", "does_not_exist", {}),)),
            Completion(text="Here's what I can tell you.", tool_calls=()),
        ]
    )
    answer = run_tutor(provider, tools, [Turn("user", "hi")])
    assert answer.reply == "Here's what I can tell you."


def test_engine_caps_tool_rounds_and_still_answers(db_session: Session) -> None:
    market, candles = FakeMarket(), FakeCandles()
    account = _account(db_session, "alex@example.com")
    tools = build_tools(db_session, account, market, candles)
    loop_turn = Completion(text="", tool_calls=(ToolCall("c", "get_portfolio_summary", {}),))
    # Six loop rounds all ask for a tool, then the forced no-tools round must produce an answer.
    provider = Scripted([loop_turn] * 6 + [Completion(text="Final answer.", tool_calls=())])
    answer = run_tutor(provider, tools, [Turn("user", "loop please")])
    assert answer.reply == "Final answer."


# --- Provider: OpenAI translation (no network) ----------------------------------------------


def _stub_client(response: Any, capture: dict[str, Any] | None = None) -> Any:
    def create(**kwargs: Any) -> Any:
        if capture is not None:
            capture.update(kwargs)
        return response

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_openai_provider_parses_tool_calls() -> None:
    function = SimpleNamespace(name="get_portfolio_summary", arguments='{"a": 1}')
    call = SimpleNamespace(id="c1", function=function)
    message = SimpleNamespace(content=None, tool_calls=[call])
    response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    capture: dict[str, Any] = {}
    provider = OpenAIProvider(api_key="unused", model="m", client=_stub_client(response, capture))

    out = provider.complete(
        system="s",
        messages=[UserMessage("hi")],
        tools=[ToolSchema("get_portfolio_summary", "desc", _NO_ARGS)],
    )

    assert out.text == ""
    assert out.tool_calls[0].name == "get_portfolio_summary"
    assert out.tool_calls[0].arguments == {"a": 1}
    # The system prompt and user turn were translated into the OpenAI message shape.
    assert capture["messages"][0] == {"role": "system", "content": "s"}
    assert capture["tool_choice"] == "auto"


def test_openai_provider_returns_plain_text() -> None:
    message = SimpleNamespace(content="Hello there.", tool_calls=None)
    response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    provider = OpenAIProvider(api_key="unused", model="m", client=_stub_client(response))
    out = provider.complete(system="s", messages=[UserMessage("hi")], tools=[])
    assert out.text == "Hello there."
    assert out.tool_calls == ()


def test_openai_provider_wraps_api_errors() -> None:
    def boom(**_kwargs: Any) -> Any:
        raise OpenAIError("upstream is down")

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=boom)))
    provider = OpenAIProvider(api_key="unused", model="m", client=client)
    with pytest.raises(TutorError):
        provider.complete(system="s", messages=[UserMessage("hi")], tools=[])


# --- Live check against the real model (opt-in) ---------------------------------------------


@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="set OPENAI_API_KEY to run the live tutor check",
)
def test_live_tutor_cites_only_tool_numbers_and_refuses_advice() -> None:
    get_tutor_provider.cache_clear()
    provider = get_tutor_provider()
    assert provider is not None

    # A tiny fake tool set, so this needs only an OpenAI key, no market data or DB.
    summary: dict[str, Any] = {
        "cash": 500.0,
        "total_value": 525.0,
        "total_gain_loss": 25.0,
        "total_gain_loss_percent": 5.0,
        "holdings": [{"symbol": "AAPL", "market_value": 25.0}],
    }
    tools = [
        Tool(
            schema=ToolSchema("get_portfolio_summary", "The user's whole account.", _NO_ARGS),
            run=lambda _args: summary,
        )
    ]

    question = "How much cash do I have, and how am I doing?"
    money = run_tutor(provider, tools, [Turn("user", question)])
    assert unaccounted_numbers(money.reply, [summary]) == []

    advice = run_tutor(provider, tools, [Turn("user", "Should I buy more Apple right now?")])
    lowered = advice.reply.lower()
    assert "you should buy" not in lowered
    assert "i recommend buying" not in lowered
