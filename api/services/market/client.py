"""Finnhub client with a small in-memory quote cache.

Caching keeps us well under Finnhub's free tier: a quote for a symbol is reused
for a few seconds instead of hitting the API on every request. Every network
failure is turned into a ``MarketError`` with a user-safe message so no raw
provider error ever reaches the user.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import httpx

from config import get_settings

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"
DEFAULT_TTL_SECONDS = 15.0


class MarketError(Exception):
    """A market-data lookup failed. The message is safe to show to a user."""


@dataclass(frozen=True)
class Quote:
    """A point-in-time quote for one symbol, as returned to the app."""

    symbol: str
    price: float
    change: float
    percent_change: float
    high: float
    low: float
    open: float
    previous_close: float


@dataclass
class _CacheEntry:
    quote: Quote
    expires_at: float


class MarketClient:
    """Fetches quotes from Finnhub and caches them briefly in memory."""

    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.Client | None = None,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        base_url: str = FINNHUB_BASE_URL,
    ) -> None:
        self._api_key = api_key
        self._ttl = ttl_seconds
        self._client = client or httpx.Client(base_url=base_url, timeout=10.0)
        self._owns_client = client is None
        self._cache: dict[str, _CacheEntry] = {}

    def get_quote(self, symbol: str) -> Quote:
        """Return a quote for ``symbol``, served from cache when still fresh."""
        symbol = symbol.upper()
        now = time.monotonic()

        cached = self._cache.get(symbol)
        if cached is not None and cached.expires_at > now:
            return cached.quote

        quote = self._fetch_quote(symbol)
        self._cache[symbol] = _CacheEntry(quote=quote, expires_at=now + self._ttl)
        return quote

    def _fetch_quote(self, symbol: str) -> Quote:
        try:
            response = self._client.get("/quote", params={"symbol": symbol, "token": self._api_key})
            response.raise_for_status()
            data: Any = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                raise MarketError(
                    "Hit the market data rate limit. Give it a few seconds and try again."
                ) from exc
            raise MarketError(f"The market data provider errored out for {symbol}.") from exc
        except httpx.HTTPError as exc:
            raise MarketError(f"Couldn't reach the market data provider for {symbol}.") from exc

        # Finnhub returns all-zero fields for an unknown symbol.
        if not isinstance(data, dict) or not data.get("c"):
            raise MarketError(f"No quote available for {symbol}.")

        return Quote(
            symbol=symbol,
            price=float(data["c"]),
            change=float(data.get("d") or 0.0),
            percent_change=float(data.get("dp") or 0.0),
            high=float(data.get("h") or 0.0),
            low=float(data.get("l") or 0.0),
            open=float(data.get("o") or 0.0),
            previous_close=float(data.get("pc") or 0.0),
        )

    def close(self) -> None:
        """Close the underlying HTTP client if this instance owns it."""
        if self._owns_client:
            self._client.close()


@lru_cache
def get_market_client() -> MarketClient:
    """Return the process-wide market client (shares one cache and HTTP pool)."""
    return MarketClient(api_key=get_settings().finnhub_api_key)
