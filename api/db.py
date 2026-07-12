"""Database engine, session factory, and the per-request session dependency.

The engine is created once for the process. ``get_db`` hands each request its own
session and closes it when the request finishes. Route handlers (and the sim
layer) commit explicitly, so this module stays free of business logic.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config import get_settings

engine = create_engine(get_settings().sqlalchemy_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Yield a database session for one request, closing it afterwards."""
    with SessionLocal() as session:
        yield session
