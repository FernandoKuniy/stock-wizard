"""Unit tests for the Twelve Data candle client: parsing, caching, and errors.

Twelve Data is faked with an ``httpx.MockTransport`` so no test hits the network.
"""

from __future__ import annotations

import httpx
import pytest

from services.market.candles import FETCH_OUTPUTSIZE, CandleClient
from services.market.client import MarketError


def _timeseries_payload() -> dict[str, object]:
    return {
        "meta": {"symbol": "AAPL", "interval": "1day"},
        "status": "ok",
        # Twelve Data returns newest bar first; the client should flip that.
        "values": [
            {"datetime": "2026-07-10", "close": "210.5"},
            {"datetime": "2026-07-09", "close": "208.0"},
        ],
    }


def _client_with(handler: httpx.MockTransport, api_key: str | None = "td-key") -> CandleClient:
    http = httpx.Client(transport=handler, base_url="https://twelvedata.test")
    return CandleClient(api_key, client=http)


def test_get_candles_parses_oldest_first() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["symbol"] == "AAPL"
        assert request.url.params["apikey"] == "td-key"
        return httpx.Response(200, json=_timeseries_payload())

    client = _client_with(httpx.MockTransport(handler))
    candles = client.get_candles("aapl")

    assert candles.symbol == "AAPL"
    assert [p.date for p in candles.points] == ["2026-07-09", "2026-07-10"]
    assert candles.points[-1].close == 210.5


def test_get_candles_is_cached() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_timeseries_payload())

    client = _client_with(httpx.MockTransport(handler))
    client.get_candles("AAPL")
    client.get_candles("AAPL")
    assert calls == 1


def test_one_fetch_serves_both_the_short_chart_and_the_long_history() -> None:
    """We always pull the long window and slice it, rather than paying for two calls."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.params["outputsize"] == str(FETCH_OUTPUTSIZE)
        return httpx.Response(200, json=_timeseries_payload())

    client = _client_with(httpx.MockTransport(handler))

    long_window = client.get_candles("AAPL", outputsize=FETCH_OUTPUTSIZE)
    short_window = client.get_candles("AAPL", outputsize=1)

    assert calls == 1  # the free tier thanks us
    assert len(long_window.points) == 2  # the payload only has two bars to give
    # The short window is the tail of the same data, newest bar last.
    assert [p.date for p in short_window.points] == ["2026-07-10"]


def test_missing_api_key_raises() -> None:
    client = _client_with(httpx.MockTransport(lambda request: httpx.Response(200)), api_key=None)
    with pytest.raises(MarketError):
        client.get_candles("AAPL")


def test_status_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "error", "code": 400, "message": "bad symbol"})

    client = _client_with(httpx.MockTransport(handler))
    with pytest.raises(MarketError):
        client.get_candles("NOPE")


def test_rate_limit_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"status": "error", "code": 429, "message": "limit"})

    client = _client_with(httpx.MockTransport(handler))
    with pytest.raises(MarketError):
        client.get_candles("AAPL")


def test_network_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    client = _client_with(httpx.MockTransport(handler))
    with pytest.raises(MarketError):
        client.get_candles("AAPL")


def test_empty_values_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok", "values": []})

    client = _client_with(httpx.MockTransport(handler))
    with pytest.raises(MarketError):
        client.get_candles("AAPL")
