"""Awarding achievements: the thin step that turns computed facts into stored badges.

This is a composition layer, the same shape as ``services/portfolio.py``: the actual
decision of who earned what is the pure code in ``services/analysis/achievements.py``, and
all this does is feed it the account's data and write down anything newly earned. It reads
the account's transactions (for how long each position has been held) and the already-built
portfolio snapshot (for each holding's gain/loss), never the market directly, so awarding on
a dashboard load costs no extra provider call.

Two properties matter and both are deliberate:

- **Add-only.** A badge is inserted the first time it's earned and never removed. Selling a
  stock you held for a year doesn't undo the fact that you held it for a year, so the row
  stays. This also means a badge survives a reset, which is why ``reset`` doesn't touch this
  table: achievements are a learning record, not money.
- **Idempotent.** The unique constraint on (account_id, key) plus the "only insert keys we
  don't already have" check means the lazy re-check on every load is safe and, once a badge
  is earned, writes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Account, Achievement, Transaction
from services.analysis.achievements import (
    CATALOG,
    AccountFacts,
    Fill,
    PositionFact,
    continuous_hold_days,
    evaluate,
)
from services.portfolio import PortfolioSnapshot


@dataclass(frozen=True)
class EarnedBadge:
    """One badge as the dashboard shows it: the static copy plus whether this account has it.

    ``earned_at`` is ``None`` for a locked badge, whose ``requirement`` line tells the user
    how to earn it.
    """

    key: str
    title: str
    requirement: str
    lesson: str
    earned: bool
    earned_at: datetime | None


@dataclass(frozen=True)
class AchievementsResult:
    """The full badge list for display, plus which keys were earned on this very call.

    ``newly_awarded`` is what tells the caller a write happened, so it can commit (and only
    then), the same way the order sweep signals it settled something.
    """

    badges: list[EarnedBadge]
    newly_awarded: list[str]


def award_achievements(
    session: Session,
    account: Account,
    snapshot: PortfolioSnapshot,
    *,
    now: datetime | None = None,
) -> AchievementsResult:
    """Detect and record any achievements this account has newly earned, and return them all.

    ``now`` is injectable so tests can pin "today"; in the app it's the real clock. The facts
    come from the account's own transactions and its snapshot, both already scoped to this
    account by the caller, so one user's badges can never be computed from another's money.
    """
    moment = now if now is not None else datetime.now(UTC)
    as_of = moment.date()

    fills_by_symbol = _fills_by_symbol(session, account)
    positions = tuple(
        PositionFact(
            symbol=view.symbol,
            # A snapshot holding always reconstructs to a positive position, so hold days is
            # never None here; the ``or 0`` is just a total-function guard for mypy.
            held_days=continuous_hold_days(fills_by_symbol.get(view.symbol, []), as_of) or 0,
            gain_loss_percent=view.gain_loss_percent,
        )
        for view in snapshot.holdings
    )
    earned = evaluate(AccountFacts(positions=positions))

    # Existing badges (key -> when earned). New ones get inserted with this moment as their
    # earned_at, so the returned view is complete without a second read.
    badges_earned = {
        row.key: row.earned_at
        for row in session.scalars(select(Achievement).where(Achievement.account_id == account.id))
    }
    newly = sorted(earned - badges_earned.keys())
    for key in newly:
        session.add(Achievement(account_id=account.id, key=key, earned_at=moment))
        badges_earned[key] = moment
    if newly:
        session.flush()

    view = [
        EarnedBadge(
            key=badge.key,
            title=badge.title,
            requirement=badge.requirement,
            lesson=badge.lesson,
            earned=badge.key in badges_earned,
            earned_at=badges_earned.get(badge.key),
        )
        for badge in CATALOG
    ]
    return AchievementsResult(badges=view, newly_awarded=newly)


def _fills_by_symbol(session: Session, account: Account) -> dict[str, list[Fill]]:
    """Every trade the account has made, grouped by symbol and in time order.

    Time order (not just date order) matters for a symbol bought and sold on the same day, so
    the hold-duration walk sees the buy before the sell.
    """
    rows = session.scalars(
        select(Transaction)
        .where(Transaction.account_id == account.id)
        .order_by(Transaction.timestamp, Transaction.id)
    )
    fills: dict[str, list[Fill]] = {}
    for row in rows:
        fills.setdefault(row.symbol, []).append(
            Fill(on=row.timestamp.date(), side=row.side, quantity=row.quantity)
        )
    return fills
