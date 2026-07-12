"""Unit tests for the Finnhub client: parsing, caching, and error handling.

All Finnhub calls are faked with an ``httpx.MockTransport`` so tests never touch
the network or burn quota.
"""

from __future__ import annotations

import httpx
import pytest

from services.market.client import MarketClient, MarketError


def _payload() -> dict[str, float]:
    return {"c": 190.5, "d": 2.5, "dp": 1.3, "h": 191.0, "l": 188.0, "o": 189.0, "pc": 188.0}


def _client_with(handler: httpx.MockTransport, ttl_seconds: float = 15.0) -> MarketClient:
    http = httpx.Client(transport=handler, base_url="https://finnhub.test")
    return MarketClient("test-key", client=http, ttl_seconds=ttl_seconds)


def test_get_quote_parses_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["symbol"] == "AAPL"
        assert request.url.params["token"] == "test-key"
        return httpx.Response(200, json=_payload())

    client = _client_with(httpx.MockTransport(handler))
    quote = client.get_quote("aapl")

    assert quote.symbol == "AAPL"
    assert quote.price == 190.5
    assert quote.change == 2.5
    assert quote.percent_change == 1.3


def test_get_quote_is_cached_within_ttl() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_payload())

    client = _client_with(httpx.MockTransport(handler), ttl_seconds=60.0)
    client.get_quote("AAPL")
    client.get_quote("AAPL")

    assert calls == 1  # second read served from cache, no extra HTTP call


def test_unknown_symbol_raises_market_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # Finnhub returns all zeros for a symbol it does not know.
        return httpx.Response(200, json={"c": 0, "d": 0, "dp": 0, "h": 0, "l": 0, "o": 0, "pc": 0})

    client = _client_with(httpx.MockTransport(handler))
    with pytest.raises(MarketError):
        client.get_quote("NOPE")


def test_rate_limit_raises_market_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={})

    client = _client_with(httpx.MockTransport(handler))
    with pytest.raises(MarketError):
        client.get_quote("AAPL")


def test_network_error_raises_market_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    client = _client_with(httpx.MockTransport(handler))
    with pytest.raises(MarketError):
        client.get_quote("AAPL")


def _search_payload() -> dict[str, object]:
    return {
        "count": 3,
        "result": [
            {"symbol": "AAPL", "description": "APPLE INC", "type": "Common Stock"},
            {"symbol": "", "description": "NO SYMBOL", "type": "Common Stock"},
            {"symbol": "APLE", "description": "APPLE HOSPITALITY REIT", "type": "Common Stock"},
        ],
    }


def test_search_parses_and_skips_incomplete_rows() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["q"] == "apple"
        return httpx.Response(200, json=_search_payload())

    client = _client_with(httpx.MockTransport(handler))
    matches = client.search("apple")

    assert [m.symbol for m in matches] == ["AAPL", "APLE"]
    assert matches[0].description == "APPLE INC"


def test_search_blank_query_skips_the_network() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_search_payload())

    client = _client_with(httpx.MockTransport(handler))
    assert client.search("   ") == []
    assert calls == 0


def _profile_payload() -> dict[str, object]:
    return {
        "name": "Apple Inc",
        "ticker": "AAPL",
        "exchange": "NASDAQ NMS - GLOBAL MARKET",
        "finnhubIndustry": "Technology",
        "logo": "https://logo.test/aapl.png",
        "marketCapitalization": 2_900_000.0,
    }


def test_get_profile_parses_and_builds_blurb() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["symbol"] == "AAPL"
        return httpx.Response(200, json=_profile_payload())

    client = _client_with(httpx.MockTransport(handler))
    profile = client.get_profile("aapl")

    assert profile.name == "Apple Inc"
    assert profile.industry == "Technology"
    assert "Technology" in profile.blurb
    assert profile.market_cap == 2_900_000.0 * 1_000_000


def test_profile_is_cached() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_profile_payload())

    client = _client_with(httpx.MockTransport(handler))
    client.get_profile("AAPL")
    client.get_profile("AAPL")
    assert calls == 1


def test_unknown_profile_raises_market_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    client = _client_with(httpx.MockTransport(handler))
    with pytest.raises(MarketError):
        client.get_profile("NOPE")
