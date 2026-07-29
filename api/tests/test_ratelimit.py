"""Unit tests for the in-memory rate limiter, with the clock injected so nothing waits."""

from __future__ import annotations

from ratelimit import RateLimiter


class FakeClock:
    """A hand-cranked clock: time only moves when a test moves it."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_allows_up_to_the_limit_then_refuses() -> None:
    limiter = RateLimiter(max_calls=3, per_seconds=60, now=FakeClock())
    assert [limiter.allow("a") for _ in range(4)] == [True, True, True, False]


def test_the_window_resets_after_it_elapses() -> None:
    clock = FakeClock()
    limiter = RateLimiter(max_calls=1, per_seconds=60, now=clock)
    assert limiter.allow("a") is True
    assert limiter.allow("a") is False
    clock.t = 60.0
    assert limiter.allow("a") is True


def test_keys_are_independent() -> None:
    limiter = RateLimiter(max_calls=1, per_seconds=60, now=FakeClock())
    assert limiter.allow("a") is True
    assert limiter.allow("b") is True  # b has its own budget
    assert limiter.allow("a") is False


def test_a_refused_call_does_not_extend_the_window() -> None:
    clock = FakeClock()
    limiter = RateLimiter(max_calls=1, per_seconds=60, now=clock)
    assert limiter.allow("a") is True
    clock.t = 30.0
    assert limiter.allow("a") is False  # refused mid-window
    clock.t = 60.0  # the original window still expires on schedule
    assert limiter.allow("a") is True
