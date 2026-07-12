"""Twelve Data client for historical price candles.

Finnhub's free tier no longer serves ``/stock/candle``, so the price charts come
from Twelve Data instead. This still lives in the market layer, behind the same
``MarketError`` contract, and caches aggressively (daily bars barely move) to stay
inside the free tier. The app runs without a key; only the charts need it.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import httpx

from config import get_settings
from services.market.cache import TtlCache
from services.market.client import MarketError

TWELVE_DATA_BASE_URL = "https://api.twelvedata.com"
CANDLE_TTL_SECONDS = 60.0 * 60.0
DEFAULT_OUTPUTSIZE = 90


@dataclass(frozen=True)
class CandlePoint:
    """One daily bar, trimmed to what a simple line chart needs."""

    date: str
    close: float


@dataclass(frozen=True)
class Candles:
    """A symbol's recent daily closes, oldest bar first."""

    symbol: str
    points: list[CandlePoint]


class CandleClient:
    """Fetches daily candles from Twelve Data, cached in memory."""

    def __init__(
        self,
        api_key: str | None,
        *,
        client: httpx.Client | None = None,
        ttl_seconds: float = CANDLE_TTL_SECONDS,
        base_url: str = TWELVE_DATA_BASE_URL,
    ) -> None:
        self._api_key = api_key
        self._client = client or httpx.Client(base_url=base_url, timeout=10.0)
        self._owns_client = client is None
        self._cache: TtlCache[Candles] = TtlCache(ttl_seconds)

    def get_candles(self, symbol: str, *, outputsize: int = DEFAULT_OUTPUTSIZE) -> Candles:
        """Return recent daily candles for ``symbol``, oldest bar first."""
        symbol = symbol.upper()
        key = f"{symbol}:{outputsize}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        candles = self._fetch_candles(symbol, outputsize)
        self._cache.set(key, candles)
        return candles

    def _fetch_candles(self, symbol: str, outputsize: int) -> Candles:
        if not self._api_key:
            raise MarketError("Price charts aren't set up yet.")
        try:
            response = self._client.get(
                "/time_series",
                params={
                    "symbol": symbol,
                    "interval": "1day",
                    "outputsize": str(outputsize),
                    "apikey": self._api_key,
                },
            )
            response.raise_for_status()
            data: Any = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                raise MarketError(
                    "Hit the market data rate limit. Give it a few seconds and try again."
                ) from exc
            raise MarketError(f"Couldn't load chart data for {symbol}.") from exc
        except httpx.HTTPError as exc:
            raise MarketError(f"Couldn't reach the chart data provider for {symbol}.") from exc

        # Twelve Data signals problems in the body with status "error", often on a 200.
        if not isinstance(data, dict) or data.get("status") == "error":
            if isinstance(data, dict) and data.get("code") == 429:
                raise MarketError(
                    "Hit the market data rate limit. Give it a few seconds and try again."
                )
            raise MarketError(f"No chart data available for {symbol}.")
        values = data.get("values")
        if not values:
            raise MarketError(f"No chart data available for {symbol}.")
        try:
            points = [
                CandlePoint(date=str(item["datetime"]), close=float(item["close"]))
                for item in reversed(values)
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise MarketError(f"Couldn't read chart data for {symbol}.") from exc
        return Candles(symbol=symbol, points=points)

    def close(self) -> None:
        """Close the underlying HTTP client if this instance owns it."""
        if self._owns_client:
            self._client.close()


@lru_cache
def get_candle_client() -> CandleClient:
    """Return the process-wide candle client (shares one cache and HTTP pool)."""
    return CandleClient(get_settings().twelve_data_api_key)
