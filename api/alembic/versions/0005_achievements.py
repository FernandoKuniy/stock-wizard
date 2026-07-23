"""add achievements

A badge an account has earned: a deterministic fact about how they've invested (holding
several companies, holding something a long time, sitting through a dip). The unique
constraint on (account_id, key) makes awarding idempotent, so the lazy check on every
dashboard load can safely re-attempt the same badge and only write once. Awarding is
add-only and achievements survive a reset: they're a learning record, not money.

Revision ID: 0005_achievements
Revises: 0004_orders
Create Date: 2026-07-22

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_achievements"
down_revision: str | Sequence[str] | None = "0004_orders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the achievements table, scoped to an account like every other table."""
    op.create_table(
        "achievements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column(
            "earned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("account_id", "key", name="uq_achievements_account_key"),
    )
    op.create_index("ix_achievements_account_id", "achievements", ["account_id"])


def downgrade() -> None:
    """Drop the achievements table."""
    op.drop_table("achievements")
