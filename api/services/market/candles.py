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
# Daily bars only change once a day, after the close, so holding them for hours costs us
# nothing in freshness and saves a lot of quota. The free tier allows 8 calls a minute, and
# drawing the portfolio history needs one call per symbol ever held, plus one for the index.
CANDLE_TTL_SECONDS = 60.0 * 60.0 * 6.0
# What a caller gets if they don't ask for more: about a quarter, which is what the
# stock page's price chart shows.
DEFAULT_OUTPUTSIZE = 90
# What we actually fetch, every time: roughly two years of daily bars. A request costs
# the same whether it returns 90 rows or 500, so we pull the long window once, cache it
# per symbol, and serve the short chart and the portfolio history from the same copy.
# That halves the calls we make against the free tier.
FETCH_OUTPUTSIZE = 500


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
        """Return the most recent ``outputsize`` daily candles for ``symbol``, oldest bar first.

        Asking for fewer bars is a slice of the cached long window, not a second call.
        """
        symbol = symbol.upper()
        candles = self._cache.get(symbol)
        if candles is None:
            candles = self._fetch_candles(symbol, FETCH_OUTPUTSIZE)
            self._cache.set(symbol, candles)
        if outputsize >= len(candles.points):
            return candles
        return Candles(symbol=candles.symbol, points=candles.points[-outputsize:])

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
