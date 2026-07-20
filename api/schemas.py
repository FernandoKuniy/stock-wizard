"""Pydantic request/response schemas: the app's serialization boundary.

Money and percentages arrive here as exact ``Decimal`` from the sim and analysis
layers and leave as JSON numbers rounded for display. The frontend only formats
what these carry; it never recomputes a figure (hard rule #1).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class OrderRequest(BaseModel):
    """A buy or sell, sized by share quantity ("shares") or dollars ("dollars").

    A ``market`` order fills right away at the latest quote. A ``limit`` order needs a
    ``limit_price`` and rests until the market reaches it, so it comes back as a resting
    order rather than a completed trade.
    """

    symbol: str
    side: Literal["buy", "sell"]
    mode: Literal["shares", "dollars"]
    value: Decimal
    type: Literal["market", "limit"] = "market"
    limit_price: Decimal | None = None


class QuoteOut(BaseModel):
    symbol: str
    price: float
    change: float
    percent_change: float
    high: float
    low: float
    open: float
    previous_close: float


class SymbolMatchOut(BaseModel):
    symbol: str
    description: str
    type: str


class CompanyProfileOut(BaseModel):
    symbol: str
    name: str
    exchange: str
    industry: str
    logo: str
    market_cap: float
    blurb: str


class StockOut(BaseModel):
    quote: QuoteOut
    profile: CompanyProfileOut | None


class NewsItemOut(BaseModel):
    """One recent article about a company. ``date`` is an ISO date, or "" if the provider
    omitted it. The numbers inside a headline are the source's words, not our figures."""

    headline: str
    summary: str
    source: str
    url: str
    date: str


class CandlePointOut(BaseModel):
    date: str
    close: float


class CandlesOut(BaseModel):
    symbol: str
    points: list[CandlePointOut]


class HoldingOut(BaseModel):
    """One holding. Price-derived fields are null when a live quote is unavailable."""

    symbol: str
    quantity: float
    avg_cost: float
    cost_basis: float
    price: float | None
    market_value: float | None
    gain_loss: float | None
    gain_loss_percent: float | None
    weight: float | None


class PortfolioOut(BaseModel):
    cash: float
    starting_balance: float
    total_value: float
    total_cost_basis: float
    total_gain_loss: float
    total_gain_loss_percent: float
    cash_weight: float
    holdings: list[HoldingOut]
    # Symbols we couldn't get a live price for just now. They're counted in the totals at
    # what they cost, so a flaky quote can't quietly shrink the portfolio and read as a
    # loss the user never took. The UI says so rather than pretending the number is fresh.
    unpriced_symbols: list[str]


class HistoryPointOut(BaseModel):
    """One day on the performance chart. ``benchmark`` is null if we have no index price."""

    date: str
    portfolio: float
    benchmark: float | None


class BenchmarkComparisonOut(BaseModel):
    """Where the user ended up versus the same money left in the index."""

    portfolio_value: float
    benchmark_value: float
    # Positive means the user is ahead of the index, in dollars.
    difference: float
    portfolio_percent: float
    benchmark_percent: float


class PortfolioHistoryOut(BaseModel):
    starting_balance: float
    benchmark_symbol: str | None
    points: list[HistoryPointOut]
    comparison: BenchmarkComparisonOut | None


class TransactionOut(BaseModel):
    id: int
    symbol: str
    side: str
    quantity: float
    price: float
    total: float
    timestamp: datetime


class OrderOut(BaseModel):
    """A limit order: the price it's waiting for, and how it ended up.

    ``cancel_reason`` is set only when we cancelled it on the user's behalf (the cash or the
    shares were gone by the time the price arrived), so the UI can explain rather than just
    show a status.
    """

    id: int
    symbol: str
    side: str
    quantity: float
    limit_price: float
    status: str
    created_at: datetime
    resolved_at: datetime | None
    cancel_reason: str | None


class OrderResultOut(BaseModel):
    """What came of placing an order. A market order fills immediately and comes back as a
    ``transaction``; a limit order rests and comes back as an ``order``. Exactly one is set."""

    transaction: TransactionOut | None = None
    order: OrderOut | None = None
    cash: float


class TutorMessage(BaseModel):
    """One turn of the tutor conversation. The thread lives on the client and is sent back each
    time, so the tutor is stateless here: no thread is stored server-side."""

    role: Literal["user", "assistant"]
    content: str


class TutorRequest(BaseModel):
    """The conversation so far, ending with the user's latest question."""

    messages: list[TutorMessage]


class TutorReplyOut(BaseModel):
    reply: str


class WatchlistAddRequest(BaseModel):
    """A symbol to start tracking. Validated against a live quote before it's stored, so
    we never save a ticker that doesn't resolve."""

    symbol: str


class WatchlistItemOut(BaseModel):
    """One watched symbol with a live quote for the list. ``price`` and ``percent_change``
    are null when the quote is unavailable, so a flaky provider reads as "unknown" rather
    than blocking the whole list (the same treatment holdings get)."""

    symbol: str
    price: float | None
    percent_change: float | None
