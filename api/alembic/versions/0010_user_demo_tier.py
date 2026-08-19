"""add the demo tier to users

A second, publishable invite code opens a "demo" account: everything in the app works, but the
AI tutor (the one route that costs real money per call) has a small lifetime allowance, after
which the UI points the user at the author's site to ask for a full code.

Both columns live on ``users`` rather than ``accounts`` on purpose. Resetting an account wipes
its money, and a counter kept there would hand out a fresh allowance on every reset. Existing
rows backfill to the full tier with nothing spent, so anyone already invited is unaffected.

Revision ID: 0010_user_demo_tier
Revises: 0009_recurring_investments
Create Date: 2026-08-19

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_user_demo_tier"
down_revision: str | Sequence[str] | None = "0009_recurring_investments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the demo flag and the lifetime tutor counter, both defaulted for existing rows."""
    op.add_column(
        "users",
        sa.Column("is_demo", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("tutor_messages_used", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )


def downgrade() -> None:
    """Drop both columns, putting every user back on a single tier."""
    op.drop_column("users", "tutor_messages_used")
    op.drop_column("users", "is_demo")
