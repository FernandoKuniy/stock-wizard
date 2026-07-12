"""Application configuration.

Values are loaded from the environment, or from `api/.env` in local development.
Never log or echo these values: they hold secrets (the Finnhub key and the DB URL).
"""

from decimal import Decimal
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    """Typed application settings, read once from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    finnhub_api_key: str
    database_url: str
    # Twelve Data serves the historical candles Finnhub's free tier no longer does.
    # Optional: the app still runs without it; only the price charts need it.
    twelve_data_api_key: str | None = None
    # The frontend dev server origin, allowed through CORS.
    frontend_origin: str = "http://localhost:3000"
    # The single seeded account used until real auth lands in M2.
    seed_user_email: str = "demo@stockwizard.local"
    # Fake starting cash for a new account. A round number feels less intimidating.
    starting_balance: Decimal = Decimal("100000")

    @property
    def sqlalchemy_url(self) -> str:
        """DATABASE_URL with the psycopg (v3) driver forced on.

        DATABASE_URL is a plain ``postgresql://`` string (a Supabase session-mode
        pooler URL). SQLAlchemy needs the driver named explicitly, so we rewrite it
        to ``postgresql+psycopg://`` here rather than editing the raw env value.
        """
        return (
            make_url(self.database_url)
            .set(drivername="postgresql+psycopg")
            .render_as_string(hide_password=False)
        )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide Settings, building it on first use."""
    return Settings()
