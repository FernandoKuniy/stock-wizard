"""add watchlist_items

A symbol an account is tracking, without owning it. No money is involved, so no
Numeric columns: just the account it belongs to and the ticker. One row per
(account, symbol), enforced by a unique constraint so a symbol can't be watched twice.

Revision ID: 0003_watchlist_items
Revises: 0002_user_auth_id
Create Date: 2026-07-15

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_watchlist_items"
down_revision: str | Sequence[str] | None = "0002_user_auth_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the watchlist table, scoped to an account like every other table."""
    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("account_id", "symbol", name="uq_watchlist_account_symbol"),
    )
    op.create_index("ix_watchlist_items_account_id", "watchlist_items", ["account_id"])
    op.create_index("ix_watchlist_items_symbol", "watchlist_items", ["symbol"])


def downgrade() -> None:
    """Drop the watchlist table."""
    op.drop_table("watchlist_items")
