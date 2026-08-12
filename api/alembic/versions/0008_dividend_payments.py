"""add dividend_payments

A cash dividend an account was paid for holding a stock through its ex-date. Real money in the
sim: the cash is credited when the row is written. Not a transaction (those are buys and sells);
a cash event of its own, settled lazily and add-only when the user loads their dashboard. The
unique constraint on (account, symbol, ex_date) is what makes that safe to run on every load:
a dividend is paid exactly once. RLS is enabled with no policies, matching 0006, so the table
stays closed to the PostgREST roles while our owner connection bypasses it.

Revision ID: 0008_dividend_payments
Revises: 0007_account_is_sample
Create Date: 2026-08-12

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_dividend_payments"
down_revision: str | Sequence[str] | None = "0007_account_is_sample"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the dividend_payments table, scoped to an account like every other table."""
    op.create_table(
        "dividend_payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("ex_date", sa.Date(), nullable=False),
        sa.Column("per_share", sa.Numeric(18, 4), nullable=False),
        sa.Column("shares", sa.Numeric(18, 6), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "paid_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "account_id", "symbol", "ex_date", name="uq_dividend_account_symbol_ex"
        ),
    )
    op.create_index("ix_dividend_payments_account_id", "dividend_payments", ["account_id"])
    op.create_index("ix_dividend_payments_symbol", "dividend_payments", ["symbol"])
    # Deny-by-default to the Supabase Data API roles, exactly like every other table (see 0006).
    op.execute("ALTER TABLE dividend_payments ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    """Drop the dividend_payments table."""
    op.drop_table("dividend_payments")
