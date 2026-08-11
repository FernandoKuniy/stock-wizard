"""Market-data routes: quotes, search, the stock page, candles, news, big moves, the time machine.

All read-only and account-agnostic, but signed-in only, because they spend our Finnhub and
Twelve Data quota. Every figure comes from the market or analysis layer; these routes only round.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query

from routers.common import BENCHMARK_SYMBOL, CandleDep, MarketDep, _round2, _shares, signed_in
from schemas import (
    BiggestMovesOut,
    CandlePointOut,
    CandlesOut,
    CompanyProfileOut,
    DayMoveOut,
    NewsItemOut,
    QuoteOut,
    SpreadLegOut,
    StockOut,
    SymbolMatchOut,
    WhatIfLegOut,
    WhatIfOut,
)
from services.analysis.moves import DayMove, describe_day_move
from services.analysis.whatif import NotEnoughHistory, SpreadLeg, WhatIfLeg
from services.market.client import CompanyProfile, MarketError, NewsItem, Quote
from services.portfolio import MissingHistory, build_biggest_moves, build_what_if

# How far back the time machine looks, in calendar days. Capped at two years because that is
# the candle window we already fetch and cache, so a what-if on a stock page usually costs no
# provider call at all (see services/market/candles.py).
WHAT_IF_DAYS = {"1m": 30, "6m": 182, "1y": 365, "2y": 730}
WhatIfPeriod = Literal["1m", "6m", "1y", "2y"]

router = APIRouter(dependencies=signed_in)


@router.get("/api/quote/{symbol}")
def read_quote(symbol: str, market: MarketDep) -> QuoteOut:
    """Return a live quote for ``symbol`` (e.g. AAPL)."""
    try:
        return _quote_out(market.get_quote(symbol))
    except MarketError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/api/search")
def search_symbols(q: str, market: MarketDep) -> list[SymbolMatchOut]:
    """Return ticker matches for a free-text query."""
    try:
        matches = market.search(q)
    except MarketError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [
        SymbolMatchOut(symbol=m.symbol, description=m.description, type=m.type) for m in matches
    ]


@router.get("/api/stock/{symbol}")
def read_stock(symbol: str, market: MarketDep) -> StockOut:
    """Return the current quote, best-effort company profile, and a note on any big move.

    The big-move note is worked out from the quote we already have, so it costs no extra
    provider call. It only ever says the move is unusual, never why: the day's headlines sit
    lower down the page and the reader decides whether they explain anything.
    """
    try:
        quote = market.get_quote(symbol)
    except MarketError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    try:
        profile: CompanyProfileOut | None = _profile_out(market.get_profile(symbol))
    except MarketError:
        profile = None  # the page still works with price and buy/sell
    return StockOut(
        quote=_quote_out(quote),
        profile=profile,
        big_move=describe_day_move(quote.symbol, Decimal(str(quote.percent_change))),
    )


@router.get("/api/stock/{symbol}/candles")
def read_candles(symbol: str, candles: CandleDep) -> CandlesOut:
    """Return recent daily candles for the price chart."""
    try:
        series = candles.get_candles(symbol)
    except MarketError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return CandlesOut(
        symbol=series.symbol,
        points=[CandlePointOut(date=p.date, close=p.close) for p in series.points],
    )


@router.get("/api/stock/{symbol}/news")
def read_news(symbol: str, market: MarketDep) -> list[NewsItemOut]:
    """Return recent news headlines for a symbol, for the stock page's news section.

    Thin wrapper over the market client, which already trims to the most recent handful and
    caches for a few minutes. Only a symbol the user is actually viewing is fetched, so this
    stays well under the Finnhub tier. News is a nice-to-have: a failure is a 502 and the
    stock page just hides the section rather than breaking.
    """
    try:
        items = market.get_company_news(symbol)
    except MarketError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [_news_out(item) for item in items]


@router.get("/api/stock/{symbol}/moves")
def read_biggest_moves(symbol: str, candles: CandleDep, market: MarketDep) -> BiggestMovesOut:
    """The days that did most of this stock's moving, with any headlines from those days.

    The moves come off the same cached candle window the price chart already fetched, so they
    cost nothing. The headlines are one archive fetch per symbol, held for hours, then sliced
    in code; asking day by day would have been the only genuinely new provider cost in this
    milestone. A day with no headline is the normal case and never fails the request.
    """
    try:
        moves, news = build_biggest_moves(candles, symbol, news=market)
    except MissingHistory as exc:
        raise HTTPException(
            status_code=502, detail="Couldn't load the price history for that just now."
        ) from exc

    upper = symbol.upper()
    if moves is None:
        return BiggestMovesOut(symbol=upper, trading_days=0, up=[], down=[])
    return BiggestMovesOut(
        symbol=upper,
        trading_days=moves.trading_days,
        up=[_day_move_out(move, news) for move in moves.up],
        down=[_day_move_out(move, news) for move in moves.down],
    )


@router.get("/api/stock/{symbol}/what-if")
def read_what_if(
    symbol: str,
    candles: CandleDep,
    amount: Annotated[Decimal, Query(gt=0, le=10_000_000)] = Decimal("1000"),
    period: WhatIfPeriod = "1y",
) -> WhatIfOut:
    """The time machine: what a lump sum into this stock back then would be worth now.

    Always answered next to the same money in the index, because "you'd have made $240" on
    its own reads as a nudge to buy, while next to the S&P 500 it teaches the actual lesson.
    Every figure is computed by ``services/analysis/whatif.py``; this route only rounds.
    """
    window_days = WHAT_IF_DAYS[period]
    start = date.today() - timedelta(days=window_days)
    try:
        result = build_what_if(
            candles,
            symbol,
            amount,
            start=start,
            benchmark_symbol=BENCHMARK_SYMBOL,
            window_days=window_days,
        )
    except NotEnoughHistory as exc:
        # The stock wasn't trading that far back, so there is no honest answer to give.
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MissingHistory as exc:
        raise HTTPException(
            status_code=502, detail="Couldn't load the price history for that just now."
        ) from exc

    return WhatIfOut(
        amount=_round2(result.amount),
        period=period,
        latest_on=result.stock.latest_on.isoformat(),
        stock=_what_if_leg_out(result.stock),
        benchmark=(_what_if_leg_out(result.benchmark) if result.benchmark is not None else None),
        difference=_round2(result.difference) if result.difference is not None else None,
        spread=(_spread_leg_out(result.spread) if result.spread is not None else None),
    )


def _quote_out(quote: Quote) -> QuoteOut:
    return QuoteOut(
        symbol=quote.symbol,
        price=quote.price,
        change=quote.change,
        percent_change=quote.percent_change,
        high=quote.high,
        low=quote.low,
        open=quote.open,
        previous_close=quote.previous_close,
    )


def _profile_out(profile: CompanyProfile) -> CompanyProfileOut:
    return CompanyProfileOut(
        symbol=profile.symbol,
        name=profile.name,
        exchange=profile.exchange,
        industry=profile.industry,
        logo=profile.logo,
        market_cap=profile.market_cap,
        blurb=profile.blurb,
    )


def _news_out(item: NewsItem) -> NewsItemOut:
    return NewsItemOut(
        headline=item.headline,
        summary=item.summary,
        source=item.source,
        url=item.url,
        date=item.date,
    )


def _day_move_out(move: DayMove, news: dict[str, list[NewsItem]]) -> DayMoveOut:
    day = move.on.isoformat()
    return DayMoveOut(
        date=day,
        percent_change=_round2(move.percent_change),
        close=_round2(move.close),
        news=[_news_out(item) for item in news.get(day, [])],
    )


def _what_if_leg_out(leg: WhatIfLeg) -> WhatIfLegOut:
    return WhatIfLegOut(
        symbol=leg.symbol,
        shares=_shares(leg.shares),
        bought_on=leg.bought_on.isoformat(),
        buy_price=_round2(leg.buy_price),
        value_now=_round2(leg.value_now),
        gain_loss=_round2(leg.gain_loss),
        gain_loss_percent=_round2(leg.gain_loss_percent),
    )


def _spread_leg_out(leg: SpreadLeg) -> SpreadLegOut:
    return SpreadLegOut(
        symbol=leg.symbol,
        instalments=leg.instalments,
        each=_round2(leg.each),
        shares=_shares(leg.shares),
        first_on=leg.first_on.isoformat(),
        last_on=leg.last_on.isoformat(),
        value_now=_round2(leg.value_now),
        gain_loss=_round2(leg.gain_loss),
        gain_loss_percent=_round2(leg.gain_loss_percent),
    )
