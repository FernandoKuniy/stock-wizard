"""Shared HTTP-layer pieces every router builds on.

The dependency aliases, the benchmark symbol, and the two money-to-JSON rounders. Kept here so
the routers agree on them rather than each redefining them. Nothing domain-specific lives here.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from auth import get_current_user
from db import get_db
from deps import get_current_account
from models import Account
from services.market.candles import CandleClient, get_candle_client
from services.market.client import MarketClient, get_market_client
from services.market.dividends import DividendProvider, get_dividend_provider
from services.tutor.provider import TutorProvider, get_tutor_provider

# The index we measure everyone against. SPY tracks the S&P 500, and it is just another
# symbol as far as the market layer is concerned.
BENCHMARK_SYMBOL = "SPY"

_CENTS = Decimal("0.01")

MarketDep = Annotated[MarketClient, Depends(get_market_client)]
CandleDep = Annotated[CandleClient, Depends(get_candle_client)]
DividendDep = Annotated[DividendProvider, Depends(get_dividend_provider)]
SessionDep = Annotated[Session, Depends(get_db)]
AccountDep = Annotated[Account, Depends(get_current_account)]
# None when no OpenAI key is configured; the tutor route says so plainly rather than crashing.
TutorDep = Annotated[TutorProvider | None, Depends(get_tutor_provider)]

# The market-data routes don't touch anyone's account, but they do spend our Finnhub and Twelve
# Data quota, so they're for signed-in users only. Everything under /api needs a token;
# /health is the only open door.
signed_in = [Depends(get_current_user)]


def _round2(value: Decimal) -> float:
    # Normalize -0.0 to 0.0: a tiny sub-cent residual from a fractional fill can
    # round to negative zero, which is correct but reads oddly in the JSON.
    rounded = float(value.quantize(_CENTS, rounding=ROUND_HALF_UP))
    return rounded if rounded != 0 else 0.0


def _shares(value: Decimal) -> float:
    return float(value)
