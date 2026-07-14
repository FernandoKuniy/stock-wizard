"""FastAPI application: the trading and portfolio HTTP surface.

Routes stay thin. They pull code-computed figures from the analysis layer, run
orders through the sim, and fetch prices through the market layer, then hand back
JSON. No financial figure is computed here beyond rounding for display.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import get_current_user
from config import get_settings
from db import get_db
from deps import get_current_account
from models import Account, Holding, Transaction
from schemas import (
    BenchmarkComparisonOut,
    CandlePointOut,
    CandlesOut,
    CompanyProfileOut,
    HistoryPointOut,
    HoldingOut,
    OrderRequest,
    OrderResultOut,
    PortfolioHistoryOut,
    PortfolioOut,
    QuoteOut,
    StockOut,
    SymbolMatchOut,
    TransactionOut,
)
from services.analysis.history import (
    Trade,
    ValuePoint,
    benchmark_series,
    compare_to_benchmark,
    portfolio_value_series,
)
from services.analysis.portfolio import (
    Position,
    portfolio_total_value,
    position_cost_basis,
    position_gain_loss,
    position_market_value,
    position_weights,
    total_gain_loss,
)
from services.market.candles import CandleClient, Candles, get_candle_client
from services.market.client import (
    CompanyProfile,
    MarketClient,
    MarketError,
    Quote,
    get_market_client,
)
from services.sim.engine import SimError, buy, reset, sell

app = FastAPI(title="Stock Wizard API")

# The index we measure everyone against. SPY tracks the S&P 500, and it is just another
# symbol as far as the market layer is concerned.
BENCHMARK_SYMBOL = "SPY"
# About two years of daily bars, which is the whole cached window (see candles.py).
HISTORY_OUTPUTSIZE = 500

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


@app.get("/api/portfolio")
def read_portfolio(account: AccountDep, session: SessionDep, market: MarketDep) -> PortfolioOut:
    """The dashboard payload: holdings, totals, and gain/loss, all computed in code."""
    holdings = list(
        session.scalars(
            select(Holding).where(Holding.account_id == account.id).order_by(Holding.symbol)
        )
    )

    quoted: dict[str, Decimal] = {}
    unpriced: list[str] = []
    for holding in holdings:
        try:
            quoted[holding.symbol] = Decimal(str(market.get_quote(holding.symbol).price))
        except MarketError:
            unpriced.append(holding.symbol)

    # A holding we couldn't get a quote for is carried in the totals at what it cost.
    # Leaving it out instead would shrink the portfolio by the whole position, so one
    # flaky Finnhub call would show up as a loss the user never actually took.
    for_totals = dict(quoted)
    for holding in holdings:
        if holding.symbol in unpriced:
            for_totals[holding.symbol] = holding.avg_cost

    positions = [Position(h.symbol, h.quantity, h.avg_cost) for h in holdings]
    cash = account.cash_balance
    total_value = portfolio_total_value(cash, positions, for_totals)
    gain_loss = total_gain_loss(cash, account.starting_balance, positions, for_totals)
    weights = position_weights(cash, positions, for_totals)

    total_cost_basis = Decimal(0)
    for holding in holdings:
        total_cost_basis += position_cost_basis(holding.quantity, holding.avg_cost)
    cash_weight = cash / total_value * Decimal(100) if total_value > 0 else Decimal(0)

    return PortfolioOut(
        cash=_round2(cash),
        starting_balance=_round2(account.starting_balance),
        total_value=_round2(total_value),
        total_cost_basis=_round2(total_cost_basis),
        total_gain_loss=_round2(gain_loss.absolute),
        total_gain_loss_percent=_round2(gain_loss.percent),
        cash_weight=_round2(cash_weight),
        holdings=[_holding_out(h, quoted, weights) for h in holdings],
        unpriced_symbols=unpriced,
    )


@app.get("/api/portfolio/history")
def read_portfolio_history(
    account: AccountDep, session: SessionDep, candles: CandleDep
) -> PortfolioHistoryOut:
    """The performance chart: what the account has been worth, against the S&P 500.

    Rebuilt from the transactions and real closing prices rather than read from a stored
    snapshot, so it is exact from the account's first day. See services/analysis/history.py.
    """
    rows = list(
        session.scalars(
            select(Transaction)
            .where(Transaction.account_id == account.id)
            .order_by(Transaction.timestamp)
        )
    )
    trades = [
        Trade(
            symbol=row.symbol,
            side=row.side,
            quantity=row.quantity,
            price=row.price,
            on=row.timestamp.date(),
        )
        for row in rows
    ]

    # Every symbol the account has ever touched, not just what it holds now: a stock sold
    # last month still has to be priced on the days it was held.
    closes: dict[str, dict[date, Decimal]] = {}
    for symbol in sorted({trade.symbol for trade in trades}):
        try:
            closes[symbol] = _closes(candles.get_candles(symbol, outputsize=HISTORY_OUTPUTSIZE))
        except MarketError as exc:
            # Without this symbol's prices the whole line would be wrong, and a wrong chart
            # about someone's money is worse than no chart. Say so instead of drawing it.
            raise HTTPException(
                status_code=502, detail="Couldn't load your performance history right now."
            ) from exc

    try:
        benchmark_closes = _closes(
            candles.get_candles(BENCHMARK_SYMBOL, outputsize=HISTORY_OUTPUTSIZE)
        )
    except MarketError:
        benchmark_closes = {}  # the user's own line is still correct; we just can't compare

    opened_on = account.created_at.date()
    dates = _trading_days(opened_on, benchmark_closes, closes)

    portfolio = portfolio_value_series(account.starting_balance, trades, closes, dates)
    benchmark = benchmark_series(account.starting_balance, benchmark_closes, dates)
    comparison = compare_to_benchmark(account.starting_balance, portfolio, benchmark)
    by_date: dict[date, ValuePoint] = {point.on: point for point in benchmark}

    return PortfolioHistoryOut(
        starting_balance=_round2(account.starting_balance),
        benchmark_symbol=BENCHMARK_SYMBOL if benchmark else None,
        points=[
            HistoryPointOut(
                date=point.on.isoformat(),
                portfolio=_round2(point.value),
                benchmark=_round2(by_date[point.on].value) if point.on in by_date else None,
            )
            for point in portfolio
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
    )


@app.post("/api/orders")
def create_order(
    body: OrderRequest, account: AccountDep, session: SessionDep, market: MarketDep
) -> OrderResultOut:
    """Place a market buy or sell, sized by shares or dollars."""
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


def _closes(candles: Candles) -> dict[date, Decimal]:
    """A symbol's daily closes, keyed by day, as exact Decimals for the analysis layer."""
    return {date.fromisoformat(point.date): Decimal(str(point.close)) for point in candles.points}


def _trading_days(
    opened_on: date,
    benchmark_closes: dict[date, Decimal],
    closes: dict[str, dict[date, Decimal]],
) -> list[date]:
    """The days the chart has a point for: every market day since the account opened.

    The index's own trading days are the natural calendar, since it trades whenever the
    US market is open. If we couldn't fetch it, fall back to the days the held symbols
    traded, and failing even that, to the single day the account opened.
    """
    if benchmark_closes:
        days = sorted(day for day in benchmark_closes if day >= opened_on)
    else:
        days = sorted({day for bars in closes.values() for day in bars if day >= opened_on})
    return days or [opened_on]


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


def _holding_out(
    holding: Holding, prices: dict[str, Decimal], weights: dict[str, Decimal]
) -> HoldingOut:
    cost_basis = position_cost_basis(holding.quantity, holding.avg_cost)
    price = prices.get(holding.symbol)
    if price is None:
        return HoldingOut(
            symbol=holding.symbol,
            quantity=_shares(holding.quantity),
            avg_cost=_round2(holding.avg_cost),
            cost_basis=_round2(cost_basis),
            price=None,
            market_value=None,
            gain_loss=None,
            gain_loss_percent=None,
            weight=None,
        )
    gain_loss = position_gain_loss(holding.quantity, holding.avg_cost, price)
    return HoldingOut(
        symbol=holding.symbol,
        quantity=_shares(holding.quantity),
        avg_cost=_round2(holding.avg_cost),
        cost_basis=_round2(cost_basis),
        price=_round2(price),
        market_value=_round2(position_market_value(holding.quantity, price)),
        gain_loss=_round2(gain_loss.absolute),
        gain_loss_percent=_round2(gain_loss.percent),
        weight=_round2(weights.get(holding.symbol, Decimal(0))),
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
