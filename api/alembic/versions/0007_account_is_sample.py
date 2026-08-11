"""add accounts.is_sample

Marks an account that still holds the demo sample portfolio we seed new accounts with on the
hosted demo, so the dashboard can offer "hit reset to start your own". Set when the account is
seeded, cleared on reset. Defaults false, so every existing account reads as a real one.

Revision ID: 0007_account_is_sample
Revises: 0006_enable_rls
Create Date: 2026-07-28

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_account_is_sample"
down_revision: str | Sequence[str] | None = "0006_enable_rls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the is_sample flag, defaulting existing rows to false (real accounts)."""
    op.add_column(
        "accounts",
        sa.Column("is_sample", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    """Drop the is_sample flag."""
    op.drop_column("accounts", "is_sample")
