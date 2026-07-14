"""Finnhub client with small in-memory caches.

The only place that talks to Finnhub. Caching keeps us well under the free tier:
quotes are reused for a few seconds, company profiles for a day, and search
results for a few minutes. Every network failure becomes a ``MarketError`` with a
user-safe message, so no raw provider error ever reaches the user.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import httpx

from config import get_settings
from services.market.cache import TtlCache

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"
DEFAULT_TTL_SECONDS = 15.0
PROFILE_TTL_SECONDS = 60.0 * 60.0 * 24.0
SEARCH_TTL_SECONDS = 60.0 * 5.0
MAX_SEARCH_RESULTS = 15


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


@dataclass(frozen=True)
class SymbolMatch:
    """One result from a ticker search."""

    symbol: str
    description: str
    type: str


@dataclass(frozen=True)
class CompanyProfile:
    """A company's reference data, plus a plain-language one-liner."""

    symbol: str
    name: str
    exchange: str
    industry: str
    logo: str
    market_cap: float
    blurb: str


class MarketClient:
    """Fetches quotes, profiles, and search results from Finnhub, cached in memory."""

    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.Client | None = None,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        base_url: str = FINNHUB_BASE_URL,
        profile_ttl_seconds: float = PROFILE_TTL_SECONDS,
        search_ttl_seconds: float = SEARCH_TTL_SECONDS,
    ) -> None:
        self._api_key = api_key
        self._client = client or httpx.Client(base_url=base_url, timeout=10.0)
        self._owns_client = client is None
        self._quotes: TtlCache[Quote] = TtlCache(ttl_seconds)
        self._profiles: TtlCache[CompanyProfile] = TtlCache(profile_ttl_seconds)
        self._searches: TtlCache[list[SymbolMatch]] = TtlCache(search_ttl_seconds)

    def get_quote(self, symbol: str) -> Quote:
        """Return a quote for ``symbol``, served from cache when still fresh."""
        symbol = symbol.upper()
        cached = self._quotes.get(symbol)
        if cached is not None:
            return cached
        quote = self._fetch_quote(symbol)
        self._quotes.set(symbol, quote)
        return quote

    def get_profile(self, symbol: str) -> CompanyProfile:
        """Return the company profile for ``symbol``, cached for a long while."""
        symbol = symbol.upper()
        cached = self._profiles.get(symbol)
        if cached is not None:
            return cached
        profile = self._fetch_profile(symbol)
        self._profiles.set(symbol, profile)
        return profile

    def search(self, query: str) -> list[SymbolMatch]:
        """Return ticker matches for a free-text ``query`` (empty for a blank query)."""
        query = query.strip()
        if not query:
            return []
        key = query.lower()
        cached = self._searches.get(key)
        if cached is not None:
            return cached
        matches = self._fetch_search(query)
        self._searches.set(key, matches)
        return matches

    def _fetch_quote(self, symbol: str) -> Quote:
        data = self._get("/quote", {"symbol": symbol})
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

    def _fetch_profile(self, symbol: str) -> CompanyProfile:
        data = self._get("/stock/profile2", {"symbol": symbol})
        if not isinstance(data, dict) or not data.get("name"):
            raise MarketError(f"No company profile available for {symbol}.")
        name = str(data["name"])
        exchange = str(data.get("exchange") or "").strip()
        industry = str(data.get("finnhubIndustry") or "").strip()
        return CompanyProfile(
            symbol=symbol,
            name=name,
            exchange=exchange,
            industry=industry,
            logo=str(data.get("logo") or "").strip(),
            # Finnhub reports market cap in millions of the listing currency.
            market_cap=float(data.get("marketCapitalization") or 0.0) * 1_000_000,
            blurb=_compose_blurb(name, industry, exchange),
        )

    def _fetch_search(self, query: str) -> list[SymbolMatch]:
        data = self._get("/search", {"q": query})
        results = data.get("result") if isinstance(data, dict) else None
        if not isinstance(results, list):
            return []
        matches: list[SymbolMatch] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "").strip()
            description = str(item.get("description") or "").strip()
            if not symbol or not description:
                continue
            matches.append(
                SymbolMatch(
                    symbol=symbol,
                    description=description,
                    type=str(item.get("type") or "").strip(),
                )
            )
            if len(matches) >= MAX_SEARCH_RESULTS:
                break
        return matches

    def _get(self, path: str, params: dict[str, str]) -> Any:
        try:
            response = self._client.get(path, params={**params, "token": self._api_key})
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                raise MarketError(
                    "Hit the market data rate limit. Give it a few seconds and try again."
                ) from exc
            raise MarketError("The market data provider is having trouble right now.") from exc
        except httpx.HTTPError as exc:
            raise MarketError("Couldn't reach the market data provider.") from exc

    def close(self) -> None:
        """Close the underlying HTTP client if this instance owns it."""
        if self._owns_client:
            self._client.close()


def _compose_blurb(name: str, industry: str, exchange: str) -> str:
    """Build a plain one-liner from the provider's own fields, in code, not with an LLM."""
    if industry:
        return f"{name} is a {industry} company."
    if exchange:
        return f"{name} is publicly traded on {exchange}."
    return f"{name} is a publicly traded company."


@lru_cache
def get_market_client() -> MarketClient:
    """Return the process-wide market client (shares one cache and HTTP pool)."""
    return MarketClient(api_key=get_settings().finnhub_api_key)
