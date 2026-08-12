"""Curated dividend history for the demo symbols. Plain data, no logic.

WHY THIS FILE EXISTS. Neither free tier we use serves dividend history: Finnhub's
``/stock/dividend`` is a premium endpoint (the same tier that already dropped candles), and
Twelve Data's ``/dividends`` needs its paid Grow plan. So for the invite-only demo we ship a
small, checked-in calendar for the handful of symbols the sample portfolio ever touches (see
``seed.py``), plus the S&P 500 proxy we benchmark against. It costs nothing, spends no quota,
and is deterministic, which also makes it easy to test around.

HOW TO KEEP IT HONEST. These are real dividends: the per-share amounts and the roughly
quarterly (DIS: semiannual) cadence match each company's actual payout history. The exact
ex-dates should be refreshed against the official record before anyone leans on them, and the
window naturally goes stale as "today" moves forward (a demo account only sees a dividend whose
ex-date falls inside the months it held the stock). To cover arbitrary tickers or stay current
automatically, swap this file (or the whole ``StaticDividendProvider``) for a live feed behind
``services/market/dividends.py`` (hard rule: all provider calls stay in the market layer).

NVDA amounts are the post-split ($0.01/share) figure throughout; this sim does not model the
June 2024 10-for-1 split, so using one consistent per-share amount avoids inventing a jump.

Each row is ``(ex_date_iso, per_share_dollars)``. The ex-date is the day the stock first trades
without the dividend: you must have held the shares *before* it to be paid.
"""

from __future__ import annotations

# symbol -> [(ex_date, per_share), ...], any order (the provider sorts).
DIVIDEND_HISTORY: dict[str, list[tuple[str, str]]] = {
    "AAPL": [
        ("2024-02-09", "0.24"),
        ("2024-05-10", "0.25"),
        ("2024-08-12", "0.25"),
        ("2024-11-08", "0.25"),
        ("2025-02-10", "0.25"),
        ("2025-05-12", "0.26"),
        ("2025-08-11", "0.26"),
        ("2025-11-10", "0.26"),
        ("2026-02-09", "0.26"),
        ("2026-05-11", "0.26"),
        ("2026-08-10", "0.26"),
    ],
    "MSFT": [
        ("2024-02-14", "0.75"),
        ("2024-05-15", "0.75"),
        ("2024-08-15", "0.75"),
        ("2024-11-21", "0.83"),
        ("2025-02-20", "0.83"),
        ("2025-05-15", "0.83"),
        ("2025-08-21", "0.83"),
        ("2025-11-20", "0.83"),
        ("2026-02-19", "0.83"),
        ("2026-05-21", "0.83"),
    ],
    "NVDA": [
        ("2024-03-05", "0.01"),
        ("2024-06-11", "0.01"),
        ("2024-09-12", "0.01"),
        ("2024-12-05", "0.01"),
        ("2025-03-12", "0.01"),
        ("2025-06-11", "0.01"),
        ("2025-09-11", "0.01"),
        ("2025-12-04", "0.01"),
        ("2026-03-11", "0.01"),
        ("2026-06-10", "0.01"),
    ],
    "KO": [
        ("2024-03-15", "0.485"),
        ("2024-06-14", "0.485"),
        ("2024-09-13", "0.485"),
        ("2024-11-29", "0.485"),
        ("2025-03-14", "0.51"),
        ("2025-06-13", "0.51"),
        ("2025-09-12", "0.51"),
        ("2025-11-28", "0.51"),
        ("2026-03-13", "0.51"),
        ("2026-06-12", "0.51"),
    ],
    "DIS": [
        ("2024-01-10", "0.45"),
        ("2024-07-08", "0.45"),
        ("2025-01-13", "0.50"),
        ("2025-07-14", "0.50"),
        ("2026-01-12", "0.75"),
    ],
    # The S&P 500 proxy we benchmark against. Its dividends make the "vs the index" line a fair
    # total-return comparison, not a price-only one (see services/analysis/history.py).
    "SPY": [
        ("2024-03-15", "1.60"),
        ("2024-06-21", "1.76"),
        ("2024-09-20", "1.75"),
        ("2024-12-20", "1.83"),
        ("2025-03-21", "1.63"),
        ("2025-06-20", "1.79"),
        ("2025-09-19", "1.78"),
        ("2025-12-19", "1.90"),
        ("2026-03-20", "1.70"),
        ("2026-06-19", "1.85"),
    ],
}
