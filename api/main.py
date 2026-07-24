"""FastAPI application: the trading and portfolio HTTP surface.

Routes stay thin. They pull code-computed figures from the analysis layer, run
orders through the sim, and fetch prices through the market layer, then hand back
JSON. No financial figure is computed here beyond rounding for display.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from auth import get_current_user
from config import get_settings
from db import get_db
from deps import get_current_account
from models import Account, Holding, Order, Transaction, WatchlistItem
from schemas import (
    AchievementOut,
    BenchmarkComparisonOut,
    CandlePointOut,
    CandlesOut,
    CheckupFindingOut,
    CompanyProfileOut,
    HistoryPointOut,
    HoldingOut,
    NeverSoldOut,
    NewsItemOut,
    OrderOut,
    OrderRequest,
    OrderResultOut,
    PortfolioHistoryOut,
    PortfolioOut,
    QuoteOut,
    SpreadLegOut,
    StockOut,
    SymbolMatchOut,
    TransactionOut,
    TutorReplyOut,
    TutorRequest,
    WatchlistAddRequest,
    WatchlistItemOut,
    WhatIfLegOut,
    WhatIfOut,
)
from services.achievements import EarnedBadge, award_achievements
from services.analysis.history import ValuePoint
from services.analysis.whatif import NotEnoughHistory, SpreadLeg, WhatIfLeg
from services.market.candles import CandleClient, get_candle_client
from services.market.client import (
    CompanyProfile,
    MarketClient,
    MarketError,
    Quote,
    get_market_client,
)
from services.portfolio import (
    HoldingView,
    MissingHistory,
    PortfolioSnapshot,
    build_checkup,
    build_history,
    build_sectors,
    build_snapshot,
    build_what_if,
)
from services.sim import orders as sim_orders
from services.sim.engine import SimError, buy, reset, sell
from services.tutor.engine import Turn, run_tutor
from services.tutor.provider import TutorError, TutorProvider, get_tutor_provider
from services.tutor.tools import build_tools

app = FastAPI(title="Stock Wizard API")

# The index we measure everyone against. SPY tracks the S&P 500, and it is just another
# symbol as far as the market layer is concerned.
BENCHMARK_SYMBOL = "SPY"

app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_CENTS = Decimal("0.01")

MarketDep = Annotated[MarketClient, Depends(get_market_client)]
CandleDep = Annotated[CandleClient, Depends(get_candle_client)]
SessionDep = Annotated[Session, Depends(get_db)]
AccountDep = Annotated[Account, Depends(get_current_account)]
# None when no OpenAI key is configured; the tutor route says so plainly rather than crashing.
TutorDep = Annotated[TutorProvider | None, Depends(get_tutor_provider)]

# Keep the sent-back conversation bounded so a runaway client can't drive up cost.
MAX_TUTOR_MESSAGES = 20

# How far back the time machine looks, in calendar days. Capped at two years because that is
# the candle window we already fetch and cache, so a what-if on a stock page usually costs no
# provider call at all (see services/market/candles.py).
WHAT_IF_DAYS = {"1m": 30, "6m": 182, "1y": 365, "2y": 730}
WhatIfPeriod = Literal["1m", "6m", "1y", "2y"]

# How far back the performance chart looks. "all" is the account's whole life and stays the
# default, so the tutor and anyone else calling this still get the since-you-started answer.
# Deliberately nothing shorter than a month: a one-day or one-week view of your own money is
# what makes people trade on noise, which is the exact habit the benchmark line warns against.
# A shorter period is a slice of the series we build anyway, so it costs no provider call.
HISTORY_PERIOD_DAYS = {"1m": 30, "6m": 182, "1y": 365}
HistoryPeriod = Literal["1m", "6m", "1y", "all"]

# The market-data routes don't touch anyone's account, but they do spend our Finnhub
# and Twelve Data quota, so they're for signed-in users only. Everything under /api
# needs a token; /health is the only open door.
signed_in = [Depends(get_current_user)]


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@app.get("/api/quote/{symbol}", dependencies=signed_in)
def read_quote(symbol: str, market: MarketDep) -> QuoteOut:
    """Return a live quote for ``symbol`` (e.g. AAPL)."""
    try:
        return _quote_out(market.get_quote(symbol))
    except MarketError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/search", dependencies=signed_in)
def search_symbols(q: str, market: MarketDep) -> list[SymbolMatchOut]:
    """Return ticker matches for a free-text query."""
    try:
        matches = market.search(q)
    except MarketError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [
        SymbolMatchOut(symbol=m.symbol, description=m.description, type=m.type) for m in matches
    ]


@app.get("/api/stock/{symbol}", dependencies=signed_in)
def read_stock(symbol: str, market: MarketDep) -> StockOut:
    """Return the current quote and best-effort company profile for a symbol."""
    try:
        quote = market.get_quote(symbol)
    except MarketError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    try:
        profile: CompanyProfileOut | None = _profile_out(market.get_profile(symbol))
    except MarketError:
        profile = None  # the page still works with price and buy/sell
    return StockOut(quote=_quote_out(quote), profile=profile)


@app.get("/api/stock/{symbol}/candles", dependencies=signed_in)
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


@app.get("/api/stock/{symbol}/news", dependencies=signed_in)
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
    return [
        NewsItemOut(
            headline=item.headline,
            summary=item.summary,
            source=item.source,
            url=item.url,
            date=item.date,
        )
        for item in items
    ]


@app.get("/api/stock/{symbol}/what-if", dependencies=signed_in)
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


@app.get("/api/portfolio")
def read_portfolio(account: AccountDep, session: SessionDep, market: MarketDep) -> PortfolioOut:
    """The dashboard payload: holdings, totals, and gain/loss, all computed in code."""
    _sweep_orders(session, account, market)
    holdings = list(
        session.scalars(
            select(Holding).where(Holding.account_id == account.id).order_by(Holding.symbol)
        )
    )
    snapshot = build_snapshot(holdings, account.cash_balance, account.starting_balance, market)
    achievements = _award_achievements(session, account, snapshot)

    return PortfolioOut(
        cash=_round2(snapshot.cash),
        starting_balance=_round2(snapshot.starting_balance),
        total_value=_round2(snapshot.total_value),
        total_cost_basis=_round2(snapshot.total_cost_basis),
        total_gain_loss=_round2(snapshot.total_gain_loss),
        total_gain_loss_percent=_round2(snapshot.total_gain_loss_percent),
        cash_weight=_round2(snapshot.cash_weight),
        holdings=[_holding_out(h) for h in snapshot.holdings],
        unpriced_symbols=snapshot.unpriced_symbols,
        what_moved=snapshot.what_moved,
        achievements=achievements,
    )


@app.get("/api/portfolio/checkup")
def read_portfolio_checkup(
    account: AccountDep, session: SessionDep, market: MarketDep
) -> list[CheckupFindingOut]:
    """How this account's money is spread out, as plain-English observations.

    Its own route rather than riding along on ``/api/portfolio`` like the achievements do,
    because unlike them this one *does* spend quota: it looks up a company profile per holding
    to work out the sector split. Profiles cache for a day, so it comes to roughly one call per
    symbol per day across everyone, but it should still only be paid for by the page that shows
    it. The sector lookup is skipped entirely for an account holding a single company, where
    there is no split to describe.

    Every figure comes from ``services/analysis``; this route composes nothing.
    """
    holdings = list(
        session.scalars(
            select(Holding).where(Holding.account_id == account.id).order_by(Holding.symbol)
        )
    )
    snapshot = build_snapshot(holdings, account.cash_balance, account.starting_balance, market)
    sectors = build_sectors((h.symbol for h in holdings), market) if len(holdings) > 1 else {}
    return [
        CheckupFindingOut(
            key=finding.key,
            title=finding.title,
            status=finding.status,
            detail=finding.detail,
            lesson=finding.lesson,
        )
        for finding in build_checkup(snapshot, sectors)
    ]


@app.get("/api/portfolio/history")
def read_portfolio_history(
    account: AccountDep, session: SessionDep, candles: CandleDep, period: HistoryPeriod = "all"
) -> PortfolioHistoryOut:
    """The performance chart: what the account has been worth, against the S&P 500.

    Rebuilt from the transactions and real closing prices rather than read from a stored
    snapshot, so it is exact from the account's first day. See services/analysis/history.py.

    ``period`` narrows it to one stretch. The series is built over the account's whole life
    either way and then sliced, off candles we already fetched and cached, so switching periods
    spends no provider quota.
    """
    rows = list(
        session.scalars(
            select(Transaction)
            .where(Transaction.account_id == account.id)
            .order_by(Transaction.timestamp)
        )
    )
    days = HISTORY_PERIOD_DAYS.get(period)
    try:
        history = build_history(
            rows,
            candles,
            opened_on=account.created_at.date(),
            starting_balance=account.starting_balance,
            benchmark_symbol=BENCHMARK_SYMBOL,
            since=date.today() - timedelta(days=days) if days is not None else None,
        )
    except MissingHistory as exc:
        # Without a held symbol's prices the whole line would be wrong, and a wrong chart
        # about someone's money is worse than no chart. Say so instead of drawing it.
        raise HTTPException(
            status_code=502, detail="Couldn't load your performance history right now."
        ) from exc

    by_date: dict[date, ValuePoint] = {point.on: point for point in history.benchmark}
    comparison = history.comparison

    # Both series end on the same day, so the last points are comparable. Positive means the
    # selling has worked out so far.
    never_sold: NeverSoldOut | None = None
    if history.never_sold and history.portfolio:
        held = history.never_sold[-1].value
        never_sold = NeverSoldOut(
            value=_round2(held),
            difference=_round2(history.portfolio[-1].value - held),
        )

    return PortfolioHistoryOut(
        starting_balance=_round2(account.starting_balance),
        period=period,
        baseline=_round2(history.baseline),
        benchmark_symbol=history.benchmark_symbol,
        points=[
            HistoryPointOut(
                date=point.on.isoformat(),
                portfolio=_round2(point.value),
                benchmark=_round2(by_date[point.on].value) if point.on in by_date else None,
            )
            for point in history.portfolio
        ],
        comparison=(
            BenchmarkComparisonOut(
                portfolio_value=_round2(comparison.portfolio_value),
                benchmark_value=_round2(comparison.benchmark_value),
                difference=_round2(comparison.difference),
                portfolio_percent=_round2(comparison.portfolio_percent),
                benchmark_percent=_round2(comparison.benchmark_percent),
            )
            if comparison is not None
            else None
        ),
        never_sold=never_sold,
    )


@app.post("/api/orders")
def create_order(
    body: OrderRequest, account: AccountDep, session: SessionDep, market: MarketDep
) -> OrderResultOut:
    """Place a buy or sell, sized by shares or dollars.

    A market order fills now, at the latest quote, and comes back as a transaction. A limit
    order rests until the price arrives and comes back as an order; placing one spends no
    quote quota, since nothing is priced until it fills.
    """
    if body.type == "limit":
        return _place_limit_order(session, account, body)

    try:
        txn = _execute_order(session, account, body, market)
    except SimError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MarketError as exc:
        session.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    session.commit()
    session.refresh(txn)  # populate the server-side timestamp
    return OrderResultOut(transaction=_txn_out(txn), cash=_round2(account.cash_balance))


@app.get("/api/orders")
def read_orders(account: AccountDep, session: SessionDep, market: MarketDep) -> list[OrderOut]:
    """The account's limit orders, newest first, after settling any whose price has arrived."""
    _sweep_orders(session, account, market)
    rows = session.scalars(
        select(Order)
        .where(Order.account_id == account.id)
        .order_by(Order.created_at.desc(), Order.id.desc())
    )
    return [_order_out(order) for order in rows]


@app.delete("/api/orders/{order_id}")
def cancel_order(order_id: int, account: AccountDep, session: SessionDep) -> OrderOut:
    """Cancel one of your resting limit orders."""
    try:
        order = sim_orders.cancel(session, account, order_id)
    except sim_orders.OrderNotFound as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SimError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    return _order_out(order)


@app.get("/api/transactions")
def read_transactions(account: AccountDep, session: SessionDep) -> list[TransactionOut]:
    """The full transaction history, newest first."""
    rows = session.scalars(
        select(Transaction)
        .where(Transaction.account_id == account.id)
        .order_by(Transaction.timestamp.desc(), Transaction.id.desc())
    )
    return [_txn_out(t) for t in rows]


@app.post("/api/account/reset")
def reset_account(account: AccountDep, session: SessionDep, market: MarketDep) -> PortfolioOut:
    """Wipe holdings and transactions and restore the starting cash."""
    reset(session, account)
    session.commit()
    return read_portfolio(account, session, market)


@app.get("/api/watchlist")
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


@app.post("/api/watchlist")
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


@app.delete("/api/watchlist/{symbol}", status_code=204)
def remove_from_watchlist(symbol: str, account: AccountDep, session: SessionDep) -> None:
    """Stop tracking a symbol. Removing one that isn't on the list is a no-op."""
    session.execute(
        delete(WatchlistItem)
        .where(WatchlistItem.account_id == account.id, WatchlistItem.symbol == symbol.upper())
        .execution_options(synchronize_session=False)
    )
    session.commit()


@app.post("/api/tutor")
def ask_tutor(
    body: TutorRequest,
    account: AccountDep,
    session: SessionDep,
    market: MarketDep,
    candles: CandleDep,
    provider: TutorDep,
) -> TutorReplyOut:
    """Ask the AI tutor about your own portfolio.

    The tutor reads only this account's money, through read-only tools scoped here to
    ``account``. Every figure it quotes comes from those tools (deterministic code), never
    from the model, and it teaches rather than advising. See services/tutor.
    """
    if provider is None:
        raise HTTPException(
            status_code=503,
            detail="The tutor isn't set up yet.",
        )
    if not body.messages or body.messages[-1].role != "user":
        raise HTTPException(
            status_code=400,
            detail="Send at least one message, ending with your question.",
        )

    conversation = [
        Turn(role=message.role, content=message.content)
        for message in body.messages[-MAX_TUTOR_MESSAGES:]
    ]
    tools = build_tools(session, account, market, candles, benchmark_symbol=BENCHMARK_SYMBOL)
    try:
        answer = run_tutor(provider, tools, conversation)
    except (MarketError, TutorError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return TutorReplyOut(reply=answer.reply)


def _sweep_orders(session: Session, account: Account, market: MarketClient) -> None:
    """Settle any resting limit orders whose price has arrived.

    This is the app's stand-in for a background job: orders get looked at when the user
    looks at their money. Committing inside a GET is deliberate, because a fill is a real
    change to the account, not a read. A symbol we can't price is skipped, never filled.
    """
    if sim_orders.sweep(session, account, market):
        session.commit()


def _award_achievements(
    session: Session, account: Account, snapshot: PortfolioSnapshot
) -> list[AchievementOut]:
    """Detect any newly-earned habit badges from the snapshot in hand, and return them all.

    Same lazy, no-cron shape as the order sweep: badges are checked when the user loads their
    dashboard, off data already fetched, so it costs no provider call. We commit only when a
    badge was actually earned, so a steady-state load stays a pure read.
    """
    result = award_achievements(session, account, snapshot)
    if result.newly_awarded:
        session.commit()
    return [_achievement_out(badge) for badge in result.badges]


def _achievement_out(badge: EarnedBadge) -> AchievementOut:
    return AchievementOut(
        key=badge.key,
        title=badge.title,
        requirement=badge.requirement,
        lesson=badge.lesson,
        earned=badge.earned,
        earned_at=badge.earned_at,
    )


def _place_limit_order(session: Session, account: Account, body: OrderRequest) -> OrderResultOut:
    """Rest a limit order. No quote is needed: nothing is priced until it fills."""
    if body.limit_price is None:
        raise HTTPException(status_code=400, detail="A limit order needs a limit price.")
    try:
        order = sim_orders.place(
            session,
            account,
            body.symbol,
            side=body.side,
            limit_price=body.limit_price,
            quantity=body.value if body.mode == "shares" else None,
            amount=body.value if body.mode == "dollars" else None,
        )
    except SimError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    session.refresh(order)  # populate the server-side timestamp
    return OrderResultOut(order=_order_out(order), cash=_round2(account.cash_balance))


def _order_out(order: Order) -> OrderOut:
    return OrderOut(
        id=order.id,
        symbol=order.symbol,
        side=order.side,
        quantity=_shares(order.quantity),
        limit_price=_round2(order.limit_price),
        status=order.status,
        created_at=order.created_at,
        resolved_at=order.resolved_at,
        cancel_reason=order.cancel_reason,
    )


def _execute_order(
    session: Session, account: Account, body: OrderRequest, market: MarketClient
) -> Transaction:
    if body.side == "buy":
        if body.mode == "shares":
            return buy(session, account, body.symbol, quantity=body.value, market=market)
        return buy(session, account, body.symbol, amount=body.value, market=market)
    if body.mode == "shares":
        return sell(session, account, body.symbol, quantity=body.value, market=market)
    return sell(session, account, body.symbol, amount=body.value, market=market)


def _holding_out(view: HoldingView) -> HoldingOut:
    """Round a computed holding for display. ``None`` price-derived fields stay ``None``."""
    return HoldingOut(
        symbol=view.symbol,
        quantity=_shares(view.quantity),
        avg_cost=_round2(view.avg_cost),
        cost_basis=_round2(view.cost_basis),
        price=_round2(view.price) if view.price is not None else None,
        market_value=_round2(view.market_value) if view.market_value is not None else None,
        gain_loss=_round2(view.gain_loss) if view.gain_loss is not None else None,
        gain_loss_percent=(
            _round2(view.gain_loss_percent) if view.gain_loss_percent is not None else None
        ),
        weight=_round2(view.weight) if view.weight is not None else None,
    )


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


def _txn_out(txn: Transaction) -> TransactionOut:
    return TransactionOut(
        id=txn.id,
        symbol=txn.symbol,
        side=txn.side,
        quantity=_shares(txn.quantity),
        price=_round2(txn.price),
        total=_round2(txn.quantity * txn.price),
        timestamp=txn.timestamp,
    )


def _round2(value: Decimal) -> float:
    # Normalize -0.0 to 0.0: a tiny sub-cent residual from a fractional fill can
    # round to negative zero, which is correct but reads oddly in the JSON.
    rounded = float(value.quantize(_CENTS, rounding=ROUND_HALF_UP))
    return rounded if rounded != 0 else 0.0


def _shares(value: Decimal) -> float:
    return float(value)
