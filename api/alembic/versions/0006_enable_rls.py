"""enable row level security on every table (deny-by-default)

Defense in depth against Supabase's Data API. We reach Postgres over a direct pooler
connection as the ``postgres`` role, so RLS never runs on our own queries (that role owns
these tables and has BYPASSRLS). But Supabase also exposes an auto-generated PostgREST Data
API over the ``public`` schema, reachable with the publishable key we ship to the browser.
With RLS off and the default grants in place, that API lets anyone read and write every
table straight past our API's account scoping.

Turning the Data API off in project settings is the primary fix. This migration is the
belt-and-suspenders one: enabling RLS with NO policies denies the ``anon`` and
``authenticated`` roles by default, so the hole stays closed even if the Data API is ever
re-enabled. It does not affect our own API, whose ``postgres`` role bypasses RLS, nor the
frontend, which only uses Supabase for auth and never queries a table directly.

Revision ID: 0006_enable_rls
Revises: 0005_achievements
Create Date: 2026-07-28

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006_enable_rls"
down_revision: str | Sequence[str] | None = "0005_achievements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Every table that holds account data. No policies are added: an empty policy set under RLS
# denies all rows to the PostgREST roles, which is exactly what we want, while our owner
# connection is unaffected.
_TABLES = (
    "users",
    "accounts",
    "holdings",
    "transactions",
    "orders",
    "watchlist_items",
    "achievements",
)


def upgrade() -> None:
    """Enable RLS on every account table, with no policies (deny by default)."""
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    """Disable RLS again, restoring the pre-migration state."""
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
