"""Dividend history, behind a swappable provider so the source can change without callers.

Same shape as the rest of the market layer: a ``Protocol`` for the slice we use, a frozen
dataclass for the value, and an ``lru_cache`` factory for the process-wide instance. The only
provider today reads the curated calendar in ``dividend_data.py`` (see that file for why we
don't fetch dividends live). A symbol we have no data for returns an empty list, which is the
truthful answer "no dividends on record", never an error, so an off-list ticker simply accrues
nothing rather than breaking a page.

To cover arbitrary symbols later, add a provider here that calls a real feed (Twelve Data's
paid tier, say) and swap ``get_dividend_provider``. Nothing outside this module changes: the
settlement in ``services/sim/dividends.py`` and the history math both depend only on the
``DividendProvider`` shape below.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import lru_cache
from typing import Protocol

from services.market.dividend_data import DIVIDEND_HISTORY


@dataclass(frozen=True)
class DividendEvent:
    """One cash dividend: how much per share, and the ex-date you had to hold before to get it."""

    symbol: str
    ex_date: date
    amount: Decimal  # cash per share, in dollars


class DividendProvider(Protocol):
    """The slice callers need: every dividend on record for a symbol, oldest ex-date first."""

    def get_dividends(self, symbol: str) -> list[DividendEvent]: ...


class StaticDividendProvider:
    """Serves dividends from a checked-in calendar. Swappable for a live feed (see module doc)."""

    def __init__(self, data: Mapping[str, Sequence[tuple[str, str]]] | None = None) -> None:
        source = DIVIDEND_HISTORY if data is None else data
        self._by_symbol: dict[str, list[DividendEvent]] = {
            symbol.upper(): sorted(
                (
                    DividendEvent(symbol.upper(), date.fromisoformat(ex), Decimal(amount))
                    for ex, amount in rows
                ),
                key=lambda event: event.ex_date,
            )
            for symbol, rows in source.items()
        }

    def get_dividends(self, symbol: str) -> list[DividendEvent]:
        """Every dividend on record for ``symbol``, oldest first. Empty when we have none."""
        return list(self._by_symbol.get(symbol.upper(), []))


@lru_cache
def get_dividend_provider() -> DividendProvider:
    """Return the process-wide dividend provider."""
    return StaticDividendProvider()
