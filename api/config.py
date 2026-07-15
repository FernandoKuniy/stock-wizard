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
    # The Supabase project URL, e.g. https://abcdefgh.supabase.co. Not a secret: it
    # only locates the project's public JWKS, which is how we verify access tokens.
    supabase_url: str
    # Twelve Data serves the historical candles Finnhub's free tier no longer does.
    # Optional: the app still runs without it; only the price charts need it.
    twelve_data_api_key: str | None = None
    # The AI tutor's model, reached through the OpenAI API. Optional: the app still runs
    # without a key, and the tutor endpoint says so plainly. The provider lives behind an
    # interface (services/tutor), so the model is a config value, never baked into code.
    openai_api_key: str | None = None
    tutor_model: str = "gpt-5.4-nano"
    # The frontend dev server origin, allowed through CORS.
    frontend_origin: str = "http://localhost:3000"
    # Fake starting cash for a new account. A round number feels less intimidating.
    starting_balance: Decimal = Decimal("100000")

    @property
    def supabase_jwks_url(self) -> str:
        """Where Supabase publishes the public keys that signed our users' tokens."""
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @property
    def supabase_issuer(self) -> str:
        """The ``iss`` claim every token from this project must carry."""
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

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
