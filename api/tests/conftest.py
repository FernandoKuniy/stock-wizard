"""Test setup shared across the suite.

Provide dummy env values so importing app modules (which read Settings) never
depends on a real `.env`. `setdefault` means a real environment still wins.
"""

import os

os.environ.setdefault("FINNHUB_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/stockwiz_test")
