"""Alembic migration environment.

The database URL comes from application settings (env / api/.env), not from
alembic.ini, so no secret ever lives in a committed file. The psycopg driver is
forced on via Settings.sqlalchemy_url.
"""

from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context
from config import get_settings
from models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a DBAPI connection, emitting SQL to stdout."""
    context.configure(
        url=get_settings().sqlalchemy_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    connectable = create_engine(get_settings().sqlalchemy_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
