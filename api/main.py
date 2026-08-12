"""FastAPI application: the trading and portfolio HTTP surface.

This module is just the composition root. It builds the app, wires CORS, exposes the health
check, and includes one router per domain from ``routers/``. The routes themselves, and the
serializers that round money for display, live in those router modules. No financial figure is
computed anywhere in this layer beyond that rounding.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from config import get_settings
from routers import account, orders, portfolio, stock, tutor, watchlist
from routers.common import SessionDep

app = FastAPI(title="Stock Wizard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. The only endpoint that needs no token."""
    return {"status": "ok"}


@app.get("/health/ready")
def ready(session: SessionDep) -> dict[str, str]:
    """Readiness probe: confirms the database is reachable.

    Also what the keep-warm ping hits, since touching the DB holds both the free web instance
    and the Supabase project awake (a query resets Supabase's idle-pause timer). Open, like
    ``/health``: it reveals only whether the database answers, never any data.
    """
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable.") from exc
    return {"status": "ready"}


# One router per domain. Order is cosmetic; paths don't overlap.
app.include_router(stock.router)
app.include_router(portfolio.router)
app.include_router(orders.router)
app.include_router(watchlist.router)
app.include_router(tutor.router)
app.include_router(account.router)
