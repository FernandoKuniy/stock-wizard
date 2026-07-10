"""FastAPI application entry point.

M0 exposes just a health check and a single live quote, proving the market-data
path works end to end. The trading and portfolio endpoints arrive in M1.
"""

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from services.market.client import MarketClient, MarketError, Quote, get_market_client

app = FastAPI(title="Stock Wizard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@app.get("/api/quote/{symbol}")
def read_quote(
    symbol: str,
    market: Annotated[MarketClient, Depends(get_market_client)],
) -> Quote:
    """Return a live quote for ``symbol`` (e.g. AAPL)."""
    try:
        return market.get_quote(symbol)
    except MarketError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
