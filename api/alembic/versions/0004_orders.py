"""add orders (limit orders)

A limit order rests until the market reaches the price the user asked for. Nothing is
reserved at placement: cash moves only at fill, so no existing money column changes.
``transaction_id`` links a filled order to the trade it became, and ``cancel_reason``
records why we cancelled one on the user's behalf (e.g. the cash was gone by the time
the price crossed).

Revision ID: 0004_orders
Revises: 0003_watchlist_items
Create Date: 2026-07-15

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_orders"
down_revision: str | Sequence[str] | None = "0003_watchlist_items"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the orders table, scoped to an account like every other table."""
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("side", sa.String(length=4), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("limit_price", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transaction_id", sa.Integer(), sa.ForeignKey("transactions.id"), nullable=True),
        sa.Column("cancel_reason", sa.String(length=200), nullable=True),
        sa.CheckConstraint("side in ('buy', 'sell')", name="ck_orders_side"),
        sa.CheckConstraint("status in ('open', 'filled', 'cancelled')", name="ck_orders_status"),
    )
    op.create_index("ix_orders_account_id", "orders", ["account_id"])
    op.create_index("ix_orders_symbol", "orders", ["symbol"])


def downgrade() -> None:
    """Drop the orders table."""
    op.drop_table("orders")
