"""A tiny in-memory, per-key rate limiter.

Keeps the app's "no background job, no Redis" shape: it counts calls per key in a fixed
time window, in process. That's enough to stop one account from looping the tutor and
running up the OpenAI bill on a single-instance deploy; a multi-instance deploy would want
a shared store instead. Pure and clock-injectable, so it unit-tests without waiting on real
time. Mirrors the in-memory TtlCache the market layer already uses.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class _Window:
    count: int
    resets_at: float


class RateLimiter:
    """Fixed-window limiter: at most ``max_calls`` per ``per_seconds``, for each key."""

    def __init__(
        self,
        *,
        max_calls: int,
        per_seconds: float,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_calls
        self._per = per_seconds
        self._now = now
        self._windows: dict[str, _Window] = {}

    def allow(self, key: str) -> bool:
        """Record a call for ``key`` and return whether it's within the limit.

        The window opens on the first call and lasts ``per_seconds``; the call that opens it
        counts, and once ``max_calls`` is reached the rest are refused until it resets. A
        refused call does not extend the window.
        """
        now = self._now()
        window = self._windows.get(key)
        if window is None or now >= window.resets_at:
            self._windows[key] = _Window(count=1, resets_at=now + self._per)
            return True
        if window.count >= self._max:
            return False
        window.count += 1
        return True
