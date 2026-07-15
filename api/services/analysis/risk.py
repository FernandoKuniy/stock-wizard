"""Concentration, diversification, and volatility: the risk side of the "numbers".

Still the analysis layer, so still plain deterministic Python with no LLM anywhere
near it. These are the operators the AI tutor leans on to answer "how risky is this?"
and "am I putting all my eggs in one basket?", and like the rest of the layer they
take plain data in and return exact ``Decimal`` values the tutor can quote by name.

Two ideas live here:

- *Concentration* looks at a single moment: how the holdings are split among each
  other. One stock holding 90% of your positions is a big bet on one company, and the
  Herfindahl index (and the "effective number of holdings" it implies) puts a number on
  that. Cash is deliberately left out, since the question is how spread out the bets are,
  not how much is sitting on the sidelines.
- *Volatility* looks over time: how much a price bounces around, measured as the standard
  deviation of its daily returns and annualized so it reads like the figures people quote
  ("the S&P swings about 15% a year").
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

_ZERO = Decimal(0)
_HUNDRED = Decimal(100)
# The market is open about 252 days a year, so a daily figure is annualized by
# multiplying by the square root of that. This is the standard convention.
_TRADING_DAYS = 252
_UNKNOWN_SECTOR = "Unknown"


@dataclass(frozen=True)
class Concentration:
    """How concentrated the holdings are, as the tutor sees it.

    ``top_weight`` and ``sector_weights`` are percents of the holdings alone (cash is not
    counted here). ``hhi`` is the Herfindahl index over the holding weights, from near 0
    (spread thin) to 1 (everything in one position). ``effective_holdings`` is ``1 / hhi``:
    the number of equally sized positions the portfolio behaves like, which is the plain-
    language way to say the same thing ("this is really a bet on about two companies").
    """

    position_count: int
    top_symbol: str | None
    top_weight: Decimal
    hhi: Decimal
    effective_holdings: Decimal
    sector_weights: dict[str, Decimal]


def concentration(
    values: Mapping[str, Decimal], sectors: Mapping[str, str] | None = None
) -> Concentration:
    """Measure how the holdings are split among each other.

    ``values`` maps each held symbol to its current market value; positions worth nothing
    are ignored. ``sectors`` optionally maps a symbol to its sector (Finnhub's industry
    field); when given, the result carries a sector breakdown, with anything unlabelled
    grouped under "Unknown". Returns all-empty when there is nothing held.
    """
    held = {symbol: value for symbol, value in values.items() if value > _ZERO}
    total = sum(held.values(), _ZERO)
    if total <= _ZERO:
        return Concentration(
            position_count=0,
            top_symbol=None,
            top_weight=_ZERO,
            hhi=_ZERO,
            effective_holdings=_ZERO,
            sector_weights={},
        )

    fractions = {symbol: value / total for symbol, value in held.items()}
    hhi = sum((fraction * fraction for fraction in fractions.values()), _ZERO)
    top_symbol = max(fractions, key=lambda symbol: fractions[symbol])

    return Concentration(
        position_count=len(held),
        top_symbol=top_symbol,
        top_weight=fractions[top_symbol] * _HUNDRED,
        hhi=hhi,
        # hhi is > 0 here because total > 0, so the reciprocal is always defined.
        effective_holdings=Decimal(1) / hhi,
        sector_weights=_sector_weights(held, total, sectors),
    )


def daily_returns(closes: Sequence[Decimal]) -> list[Decimal]:
    """The day-over-day percentage change of a price series, oldest first.

    Each return is ``(today - yesterday) / yesterday``. A day whose previous close is zero
    or negative has no meaningful return and is skipped, so a bad bar can't blow the series
    up. ``n`` closes yield up to ``n - 1`` returns.
    """
    returns: list[Decimal] = []
    for previous, current in zip(closes, closes[1:], strict=False):
        if previous > _ZERO:
            returns.append((current - previous) / previous)
    return returns


def volatility(closes: Sequence[Decimal], *, annualize: bool = True) -> Decimal | None:
    """How much a price bounces around, as a percent. ``None`` when there isn't enough data.

    This is the sample standard deviation of the daily returns, annualized by default so it
    reads on the same scale people quote ("about 20% a year"). It needs at least two returns
    (three closes) to be meaningful; with less, there is nothing honest to report, so it
    returns ``None`` rather than a fake zero.
    """
    returns = daily_returns(closes)
    if len(returns) < 2:
        return None

    count = Decimal(len(returns))
    mean = sum(returns, _ZERO) / count
    # Sample variance (divide by n - 1): we are estimating the spread from a sample of days,
    # not measuring a whole known population.
    variance = sum(((r - mean) * (r - mean) for r in returns), _ZERO) / (count - 1)
    stdev = variance.sqrt()
    if annualize:
        stdev *= Decimal(_TRADING_DAYS).sqrt()
    return stdev * _HUNDRED


def _sector_weights(
    held: Mapping[str, Decimal], total: Decimal, sectors: Mapping[str, str] | None
) -> dict[str, Decimal]:
    """Group the held value by sector and express each as a percent of the holdings."""
    if sectors is None:
        return {}
    by_sector: dict[str, Decimal] = {}
    for symbol, value in held.items():
        sector = (sectors.get(symbol) or "").strip() or _UNKNOWN_SECTOR
        by_sector[sector] = by_sector.get(sector, _ZERO) + value
    return {sector: value / total * _HUNDRED for sector, value in by_sector.items()}
