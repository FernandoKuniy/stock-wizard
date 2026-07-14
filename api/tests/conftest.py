"""Test setup shared across the suite.

Set dummy env values before any app module reads Settings, and provide a shared
in-memory database fixture. `setdefault` means a real environment still wins.
"""

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from models import Base

os.environ.setdefault("FINNHUB_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/stockwiz_test")
os.environ.setdefault("SUPABASE_URL", "https://test-project.supabase.co")


@pytest.fixture
def db_session() -> Iterator[Session]:
    """An isolated in-memory SQLite session with the full schema created.

    SQLite is fine for the seed/sim/analysis tests: the models use only portable
    column types and the logic under test is pure Python. Postgres still runs in
    dev and prod via Alembic. A StaticPool keeps one shared in-memory connection
    so the schema persists for the life of the fixture.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
