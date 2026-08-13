"""add recurring_investments

A standing instruction to invest a fixed dollar amount in a symbol every week or month:
dollar-cost averaging made real. Settled lazily on dashboard load, filling at the latest quote
through the same primitive as a manual buy; a run the account can't afford pauses the schedule.
RLS is enabled with no policies, matching 0006, so the table stays closed to the PostgREST roles
while our owner connection bypasses it.

Revision ID: 0009_recurring_investments
Revises: 0008_dividend_payments
Create Date: 2026-08-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_recurring_investments"
down_revision: str | Sequence[str] | None = "0008_dividend_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the recurring_investments table, scoped to an account like every other table."""
    op.create_table(
        "recurring_investments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("cadence", sa.String(length=16), nullable=False),
        sa.Column("next_run_on", sa.Date(), nullable=False),
        sa.Column("last_run_on", sa.Date(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("paused_reason", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("cadence in ('weekly', 'monthly')", name="ck_recurring_cadence"),
    )
    op.create_index("ix_recurring_investments_account_id", "recurring_investments", ["account_id"])
    op.create_index("ix_recurring_investments_symbol", "recurring_investments", ["symbol"])
    # Deny-by-default to the Supabase Data API roles, exactly like every other table (see 0006).
    op.execute("ALTER TABLE recurring_investments ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    """Drop the recurring_investments table."""
    op.drop_table("recurring_investments")
