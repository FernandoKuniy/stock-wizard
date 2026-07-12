"""A tiny in-memory TTL cache shared by the market-data clients.

Nothing fancy: values are kept under string keys until their time-to-live passes.
This is what keeps us under the free tier, so it lives in one place and both the
quote/profile client and the candle client reuse it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class _Cached[T]:
    value: T
    expires_at: float


class TtlCache[T]:
    """Caches values under string keys for a fixed time-to-live."""

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, _Cached[T]] = {}

    def get(self, key: str) -> T | None:
        """Return the cached value for ``key`` if it is still fresh, else None."""
        entry = self._store.get(key)
        if entry is not None and entry.expires_at > time.monotonic():
            return entry.value
        return None

    def set(self, key: str, value: T) -> None:
        """Cache ``value`` under ``key`` until the TTL elapses."""
        self._store[key] = _Cached(value=value, expires_at=time.monotonic() + self._ttl)
