# Decision Log

A running record of decisions that diverge from the original plan, newest at the top. One line each: what changed, and why. Claude Code appends here automatically when we lock in a decision that differs from what the docs described. See CLAUDE.md for the routing rules on which doc each kind of decision updates.

Format: `YYYY-MM-DD  what changed  (why)`

## Decisions

- 2026-07-12  Historical price candles come from Twelve Data, not Finnhub, because Finnhub's free tier no longer serves `/stock/candle` (returns 403); it sits behind the market client as a second provider, configured with `TWELVE_DATA_API_KEY` (optional, only the charts need it).
- 2026-07-12  Orders can be sized by dollar amount or share quantity, with fractional shares, to match modern beginner apps; the dollars↔shares conversion is computed server-side at the latest quote and shares round down to 6dp so a fill never overshoots the cash or amount.
- 2026-07-12  A minimal analysis layer (portfolio value, per-position and total P/L, weights) shipped in M1 so the dashboard's numbers come from code; the remaining operators (concentration, volatility, benchmark) and the tutor tools stay in M3.
- 2026-07-12  The M1 dashboard chart is an allocation donut (holdings + cash by weight); the portfolio value-over-time line is deferred to M2 alongside the S&P 500 benchmark, since both need a time series we do not yet store.
- 2026-07-10  Backend data layer is synchronous SQLAlchemy 2.0 + Alembic on the psycopg (v3) driver, not async (the app is low-concurrency and the sim/analysis layers are pure synchronous functions; sync is simpler to test and read, and FastAPI runs sync routes in a threadpool).
- 2026-07-10  Auth for M0 and M1 is a single seeded user with no real login; real auth (Supabase Auth) lands in M2 (keeps the early milestones focused on the trading loop and tutor before adding accounts and sessions).
- 2026-07-10  Data comes from Finnhub and we run our own simulation, instead of using Alpaca's paper-trading engine for execution (Alpaca paper accounts are one-per-login and do not fan out to a multi-user app cleanly; our own cash/holdings/transactions model is simpler and multi-user native).
