"""Portfolio routes: the dashboard snapshot, the spread-of-money check-up, and the history chart.

Every number here is computed by ``services/analysis`` and ``services/portfolio``; these routes
only round for display. ``read_portfolio`` is also the payload the account reset returns, so it
lives here and the account router calls it.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Account, DividendPayment, Holding, Transaction
from routers.common import (
    BENCHMARK_SYMBOL,
    AccountDep,
    CandleDep,
    DividendDep,
    MarketDep,
    SessionDep,
    _round2,
    _shares,
)
from routers.orders import _sweep_orders
from schemas import (
    AchievementOut,
    BenchmarkComparisonOut,
    CheckupFindingOut,
    DividendOut,
    HistoryPointOut,
    HoldingOut,
    NeverSoldOut,
    PortfolioHistoryOut,
    PortfolioOut,
)
from services.achievements import EarnedBadge, award_achievements
from services.analysis.history import CashCredit, SharePayout, ValuePoint
from services.market.client import MarketClient
from services.market.dividends import DividendProvider
from services.portfolio import (
    HoldingView,
    MissingHistory,
    PortfolioSnapshot,
    build_checkup,
    build_history,
    build_returns,
    build_sectors,
    build_snapshot,
)
from services.sim import dividends as sim_dividends
from services.sim import recurring as sim_recurring

# How far back the performance chart looks. "all" is the account's whole life and stays the
# default, so the tutor and anyone else calling this still get the since-you-started answer.
# Deliberately nothing shorter than a month: a one-day or one-week view of your own money is
# what makes people trade on noise, which is the exact habit the benchmark line warns against.
# A shorter period is a slice of the series we build anyway, so it costs no provider call.
HISTORY_PERIOD_DAYS = {"1m": 30, "6m": 182, "1y": 365}
HistoryPeriod = Literal["1m", "6m", "1y", "all"]

router = APIRouter()


@router.get("/api/portfolio")
def read_portfolio(
    account: AccountDep, session: SessionDep, market: MarketDep, dividends: DividendDep
) -> PortfolioOut:
    """The dashboard payload: holdings, totals, and gain/loss, all computed in code.

    Loading the dashboard is also when resting limit orders settle, automatic investments run,
    and dividends are paid, on the same lazy, no-cron schedule: the user looks at their money, so
    we bring it up to date. Recurring buys run before dividends and the snapshot so the cash and
    holdings they value already include everything settled this load.
    """
    _sweep_orders(session, account, market)
    _sweep_recurring(session, account, market)
    _sweep_dividends(session, account, dividends)
    holdings = list(
        session.scalars(
            select(Holding).where(Holding.account_id == account.id).order_by(Holding.symbol)
        )
    )
    snapshot = build_snapshot(holdings, account.cash_balance, account.starting_balance, market)
    achievements = _award_achievements(session, account, snapshot)

    dividend_income = sim_dividends.total_dividends(session, account)
    returns = build_returns(snapshot, _account_transactions(session, account), dividend_income)

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
        is_sample=account.is_sample,
        dividend_income=_round2(dividend_income),
        realized_gain=_round2(returns.realized),
        unrealized_gain=_round2(returns.unrealized),
    )


@router.get("/api/portfolio/checkup")
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


@router.get("/api/portfolio/history")
def read_portfolio_history(
    account: AccountDep,
    session: SessionDep,
    candles: CandleDep,
    dividends: DividendDep,
    period: HistoryPeriod = "all",
) -> PortfolioHistoryOut:
    """The performance chart: what the account has been worth, against the S&P 500.

    Rebuilt from the transactions and real closing prices rather than read from a stored
    snapshot, so it is exact from the account's first day. See services/analysis/history.py.

    Dividends are folded in on both sides: the account's own payments lift its line (so the last
    point matches the dashboard total), and the index's payouts lift the benchmark, which makes
    it an honest total-return comparison rather than one that quietly flatters the dividend
    collector. Neither costs a provider call: the payments are already recorded, and the index's
    dividends come from the same static calendar (see services/market/dividends.py).

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
            dividends=_dividend_credits(session, account),
            benchmark_dividends=_benchmark_payouts(dividends, BENCHMARK_SYMBOL),
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


@router.get("/api/dividends")
def read_dividends(account: AccountDep, session: SessionDep) -> list[DividendOut]:
    """Every dividend this account has been paid, newest first.

    A pure read: dividends are settled when the dashboard loads (see ``read_portfolio``), so
    this route just lists what's already on file and never spends a provider call.
    """
    rows = session.scalars(
        select(DividendPayment)
        .where(DividendPayment.account_id == account.id)
        .order_by(DividendPayment.ex_date.desc(), DividendPayment.id.desc())
    )
    return [_dividend_out(payment) for payment in rows]


def _sweep_recurring(session: Session, account: Account, market: MarketClient) -> None:
    """Fire any automatic investment whose next run has come due.

    The recurring counterpart of the order sweep: no background job, settled when the user loads
    their money. Committing inside a GET is deliberate, since a buy is a real change to the
    account. A schedule that fired nothing leaves the load a pure read.
    """
    if sim_recurring.sweep(session, account, market):
        session.commit()


def _sweep_dividends(session: Session, account: Account, provider: DividendProvider) -> None:
    """Pay any dividend the account is owed for stock it held through the ex-date.

    The dividend counterpart of the order sweep: no background job, settled when the user loads
    their money. Committing inside a GET is deliberate, since a payment is a real change to the
    account. Idempotent, so a steady-state load pays nothing and stays a pure read.
    """
    if sim_dividends.sweep(session, account, provider):
        session.commit()


def _account_transactions(session: Session, account: Account) -> list[Transaction]:
    """This account's trades in the order they happened, for the realized-gain replay."""
    return list(
        session.scalars(
            select(Transaction)
            .where(Transaction.account_id == account.id)
            .order_by(Transaction.timestamp, Transaction.id)
        )
    )


def _dividend_credits(session: Session, account: Account) -> list[CashCredit]:
    """The account's paid dividends as dated cash inflows for the history replay."""
    rows = session.scalars(select(DividendPayment).where(DividendPayment.account_id == account.id))
    return [CashCredit(on=row.ex_date, amount=row.amount) for row in rows]


def _benchmark_payouts(provider: DividendProvider, symbol: str) -> list[SharePayout]:
    """The index's own dividends, per share, so the benchmark line is total return too."""
    return [
        SharePayout(on=event.ex_date, per_share=event.amount)
        for event in provider.get_dividends(symbol)
    ]


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


def _dividend_out(payment: DividendPayment) -> DividendOut:
    return DividendOut(
        symbol=payment.symbol,
        ex_date=payment.ex_date,
        per_share=_round2(payment.per_share),
        shares=_shares(payment.shares),
        amount=_round2(payment.amount),
        paid_at=payment.paid_at,
    )


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
