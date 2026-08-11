"""FastAPI application: the trading and portfolio HTTP surface.

This module is just the composition root. It builds the app, wires CORS, exposes the health
check, and includes one router per domain from ``routers/``. The routes themselves, and the
serializers that round money for display, live in those router modules. No financial figure is
computed anywhere in this layer beyond that rounding.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from routers import account, orders, portfolio, stock, tutor, watchlist

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
    """Liveness probe. The only endpoint that needs no token."""
    return {"status": "ok"}


# One router per domain. Order is cosmetic; paths don't overlap.
app.include_router(stock.router)
app.include_router(portfolio.router)
app.include_router(orders.router)
app.include_router(watchlist.router)
app.include_router(tutor.router)
app.include_router(account.router)
