"""link users to Supabase Auth via auth_id

Identity moves from the email address to the Supabase Auth user id. ``auth_id`` is
the token's ``sub`` claim and is now the unique key we look a user up by, so the
unique constraint on ``email`` is dropped: Supabase owns email uniqueness, and the
column is only a copy kept for display.

Revision ID: 0002_user_auth_id
Revises: 0001_initial
Create Date: 2026-07-14

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_user_auth_id"
down_revision: str | Sequence[str] | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the Supabase Auth link and relax the email uniqueness it replaces."""
    op.add_column("users", sa.Column("auth_id", sa.Uuid(), nullable=True))
    op.create_index("ix_users_auth_id", "users", ["auth_id"], unique=True)

    op.drop_index("ix_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"], unique=False)


def downgrade() -> None:
    """Restore email as the unique identity and drop the Supabase Auth link."""
    op.drop_index("ix_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.drop_index("ix_users_auth_id", table_name="users")
    op.drop_column("users", "auth_id")
