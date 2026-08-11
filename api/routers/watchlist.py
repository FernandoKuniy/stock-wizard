"""Watchlist routes: symbols an account tracks without owning. No money, so no analysis layer.

Account-scoped CRUD, like everything else. A symbol whose quote fails is still returned with
null prices, so one flaky quote never hides the rest of the list.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, select

from models import WatchlistItem
from routers.common import AccountDep, MarketDep, SessionDep
from schemas import WatchlistAddRequest, WatchlistItemOut
from services.market.client import MarketClient, MarketError, Quote

router = APIRouter()


@router.get("/api/watchlist")
def read_watchlist(
    account: AccountDep, session: SessionDep, market: MarketDep, include_quotes: bool = True
) -> list[WatchlistItemOut]:
    """The account's watched symbols, each with a live quote for the list.

    A symbol whose quote fails is still returned, with null price fields, so one flaky
    quote never hides the rest of the list (the same treatment holdings get on the
    dashboard). ``include_quotes=false`` skips the quotes entirely and returns symbols
    only, for a caller that just needs to know what's watched (the stock page's star)
    without spending quote quota on tickers the user isn't actually looking at.
    """
    rows = session.scalars(
        select(WatchlistItem)
        .where(WatchlistItem.account_id == account.id)
        .order_by(WatchlistItem.symbol)
    )
    return [
        _watchlist_out(row.symbol, _safe_quote(market, row.symbol) if include_quotes else None)
        for row in rows
    ]


@router.post("/api/watchlist")
def add_to_watchlist(
    body: WatchlistAddRequest, account: AccountDep, session: SessionDep, market: MarketDep
) -> WatchlistItemOut:
    """Start tracking a symbol.

    The symbol is validated against a live quote first, so we never store a ticker that
    doesn't resolve, and the same quote is handed back for the list. Adding a symbol
    already on the list is a no-op, not an error.
    """
    symbol = body.symbol.strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="Enter a symbol to watch.")
    try:
        quote = market.get_quote(symbol)
    except MarketError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    existing = session.scalar(
        select(WatchlistItem).where(
            WatchlistItem.account_id == account.id, WatchlistItem.symbol == symbol
        )
    )
    if existing is None:
        session.add(WatchlistItem(account_id=account.id, symbol=symbol))
        session.commit()
    return _watchlist_out(symbol, quote)


@router.delete("/api/watchlist/{symbol}", status_code=204)
def remove_from_watchlist(symbol: str, account: AccountDep, session: SessionDep) -> None:
    """Stop tracking a symbol. Removing one that isn't on the list is a no-op."""
    session.execute(
        delete(WatchlistItem)
        .where(WatchlistItem.account_id == account.id, WatchlistItem.symbol == symbol.upper())
        .execution_options(synchronize_session=False)
    )
    session.commit()


def _safe_quote(market: MarketClient, symbol: str) -> Quote | None:
    """A live quote, or ``None`` if the provider can't give one right now. Lets the
    watchlist degrade one symbol at a time instead of failing the whole list."""
    try:
        return market.get_quote(symbol)
    except MarketError:
        return None


def _watchlist_out(symbol: str, quote: Quote | None) -> WatchlistItemOut:
    return WatchlistItemOut(
        symbol=symbol,
        price=quote.price if quote is not None else None,
        percent_change=quote.percent_change if quote is not None else None,
    )
