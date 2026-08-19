"""Pydantic request/response schemas: the app's serialization boundary.

Money and percentages arrive here as exact ``Decimal`` from the sim and analysis
layers and leave as JSON numbers rounded for display. The frontend only formats
what these carry; it never recomputes a figure (hard rule #1).
"""

from __future__ import annotations

from datetime import date, datetime
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


class RecurringRequest(BaseModel):
    """Set up an automatic investment: a fixed dollar amount into a symbol, weekly or monthly."""

    symbol: str
    amount: Decimal
    cadence: Literal["weekly", "monthly"]


class RecurringUpdate(BaseModel):
    """Pause (``active`` false) or resume (``active`` true) an automatic investment."""

    active: bool


class RecurringOut(BaseModel):
    """One automatic-investment schedule.

    ``next_run_on`` is when the next buy is due; ``last_run_on`` is when one last fired (null
    until the first). ``paused_reason`` is set only when we paused it because the cash was gone.
    """

    id: int
    symbol: str
    amount: float
    cadence: str
    next_run_on: date
    last_run_on: date | None
    active: bool
    paused_reason: str | None
    created_at: datetime


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
    """A stock's current price and reference data.

    ``big_move`` is set only when today's change is unusual enough to point at, and it says
    the move is big, never why. Whether the day's headlines explain it is left to the reader.
    """

    quote: QuoteOut
    profile: CompanyProfileOut | None
    big_move: str | None


class NewsItemOut(BaseModel):
    """One recent article about a company. ``date`` is an ISO date, or "" if the provider
    omitted it. The numbers inside a headline are the source's words, not our figures."""

    headline: str
    summary: str
    source: str
    url: str
    date: str


class WhatIfLegOut(BaseModel):
    """One side of a what-if: what the money bought, and what it's worth at the latest close."""

    symbol: str
    shares: float
    bought_on: str
    buy_price: float
    value_now: float
    gain_loss: float
    gain_loss_percent: float


class DayMoveOut(BaseModel):
    """One notable trading day: how far the price moved, and any headlines from that day.

    ``news`` is empty far more often than not. A day with no headline is the normal case,
    never an error, and the copy is clear that a move often has no reason you can point at.
    """

    date: str
    percent_change: float
    close: float
    news: list[NewsItemOut]


class BiggestMovesOut(BaseModel):
    """The handful of days that did most of a stock's moving over the window.

    ``trading_days`` is how many days moved at all, which is the number that makes the point.
    Either list can be empty: a stock that only ever rose has no down days.
    """

    symbol: str
    trading_days: int
    up: list[DayMoveOut]
    down: list[DayMoveOut]


class SpreadLegOut(BaseModel):
    """The same total money drip-fed monthly instead of all at once.

    ``each`` is one instalment. The instalments add up to exactly the amount, so this and the
    lump sum are genuinely the same money over the same window.
    """

    symbol: str
    instalments: int
    each: float
    shares: float
    first_on: str
    last_on: str
    value_now: float
    gain_loss: float
    gain_loss_percent: float


class WhatIfOut(BaseModel):
    """A lump sum into one stock, against the same money in the index over the same window.

    ``benchmark`` and ``difference`` are null when the index couldn't be priced over the
    same period, in which case the stock's own answer still stands. ``difference`` is
    positive when the stock beat the index. ``spread`` is the same total put in monthly
    instead, null when the window is too short to split.
    """

    amount: float
    period: str
    latest_on: str
    stock: WhatIfLegOut
    benchmark: WhatIfLegOut | None
    difference: float | None
    spread: SpreadLegOut | None


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


class AchievementOut(BaseModel):
    """One badge for the dashboard: the static teaching copy, plus whether this account has
    earned it. ``earned_at`` is null on a locked badge, whose ``requirement`` line explains
    how to earn it. Every field is written by a person; none is generated by the tutor."""

    key: str
    title: str
    requirement: str
    lesson: str
    earned: bool
    earned_at: datetime | None


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
    # One sentence naming the position behind the movement, null when nothing has moved.
    # Unrealized profit and loss on what's held right now, so it deliberately never claims to
    # explain total_gain_loss, which also contains money banked from things already sold.
    what_moved: str | None
    # Habit badges, earned and still-locked, detected from this account's own holdings and
    # trades on the same load (no extra provider call). Rides along on the portfolio payload
    # the dashboard already fetches rather than adding a route.
    achievements: list[AchievementOut]
    # True while this is the demo sample we seeded a new account with, so the dashboard can
    # offer "this is a sample, hit reset to start your own". Cleared by a reset.
    is_sample: bool
    # Every dividend dollar this account has been paid for holding its stocks, summed. Already
    # part of ``cash`` (and so ``total_value``): it's surfaced on its own so the UI can teach
    # that some of the money arrived just for holding. Zero when nothing has paid out yet.
    dividend_income: float
    # The total gain split into where it came from. ``realized_gain`` is money locked in by
    # selling; ``unrealized_gain`` is the gain still on paper in what's held now. With
    # ``dividend_income`` these three add up to ``total_gain_loss``, the same number shown as its
    # parts so a beginner can tell what they've banked from what's only on paper.
    realized_gain: float
    unrealized_gain: float


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


class CheckupFindingOut(BaseModel):
    """One observation about how a portfolio is spread out.

    ``status`` is ``ok``, ``notable`` or ``unknown``. Notable means worth understanding, not
    wrong: this app explains, it doesn't advise. ``detail`` is composed in code from figures
    the analysis layer worked out, and ``lesson`` is static copy written by a person.
    """

    key: str
    title: str
    status: str
    detail: str
    lesson: str


class NeverSoldOut(BaseModel):
    """What the account would be worth if every buy had simply been held.

    ``difference`` is the real portfolio minus this one, so positive means the selling has
    worked out so far and negative means it hasn't. It is a fact about what already happened,
    not a verdict: see the copy that renders it.
    """

    value: float
    difference: float


class PortfolioHistoryOut(BaseModel):
    """The performance chart over one stretch of time.

    ``starting_balance`` is what the account was funded with, always. ``baseline`` is where
    both lines start on *this* stretch, which is the same number over the account's whole life
    and its value on the first day of a shorter one.
    """

    starting_balance: float
    period: str
    baseline: float
    benchmark_symbol: str | None
    points: list[HistoryPointOut]
    comparison: BenchmarkComparisonOut | None
    # Only present on the whole-life view, and only for an account that has actually sold
    # something and could have afforded its buys without the proceeds.
    never_sold: NeverSoldOut | None


class TransactionOut(BaseModel):
    id: int
    symbol: str
    side: str
    quantity: float
    price: float
    total: float
    timestamp: datetime


class DividendOut(BaseModel):
    """One dividend paid into the account for holding a stock through its ex-date.

    ``shares`` and ``per_share`` are kept so the payment can be explained ("12.5 shares at
    $0.51"); ``amount`` is the cash that landed. Not a transaction: dividends are cash the
    company paid you, not something you bought or sold.
    """

    symbol: str
    ex_date: date
    per_share: float
    shares: float
    amount: float
    paid_at: datetime


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


class MeOut(BaseModel):
    """Who the caller is, and whether they've been let past the invite gate yet.

    ``provisioned`` is false for a signed-in user who hasn't redeemed a code, which is how
    the frontend decides to show the redeem screen's bare header rather than the full app
    chrome.

    ``tutor_messages_left`` is None for a full account (no limit) and a count for a demo one,
    so the tutor panel can say how many questions are left and swap in the "ask for a full
    code" banner at zero. The layout already fetches this on every render, so the panel costs
    no extra request."""

    email: str
    provisioned: bool
    is_demo: bool = False
    tutor_messages_left: int | None = None


class RedeemInviteRequest(BaseModel):
    """The invite code a signed-in user offers to unlock their account."""

    code: str


class RedeemInviteOut(BaseModel):
    """The result of redeeming: ``ok`` once the account is open (or already was).

    ``is_demo`` reports the tier the account ended up on, which is what lets the tutor's
    "already have a code?" form tell an upgrade from a no-op. Redeeming is deliberately
    forgiving (a stale or wrong code on an account that already exists is not an error), so
    the response has to say what happened rather than leaving the caller to guess."""

    status: Literal["ok"] = "ok"
    is_demo: bool = False


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
