# Decision Log

A running record of decisions that diverge from the original plan, newest at the top. One line each: what changed, and why. Claude Code appends here automatically when we lock in a decision that differs from what the docs described. See CLAUDE.md for the routing rules on which doc each kind of decision updates.

Format: `YYYY-MM-DD  what changed  (why)`

## Decisions

- 2026-07-14  M2 splits into M2a (auth) and M2b (education), with auth first, so the education UI is never built on the single-seeded-user assumption. The roadmap had listed M2 as education-only while architecture.md and this log both said auth lands in M2; auth first resolves the contradiction without renumbering M3 and M4.
- 2026-07-14  The API verifies Supabase access tokens locally against the project's public JWKS (asymmetric ES256), and rejects HS256 outright, rather than using the legacy shared JWT secret (Supabase no longer recommends the shared secret; verifying against the JWKS means the backend holds no secret at all and never calls Supabase to check a request).
- 2026-07-14  Identity moves from `users.email` to `users.auth_id` (the token's `sub`), and the unique constraint on email is dropped (Supabase Auth owns email uniqueness now; our column is a display copy). Integer surrogate keys stay, so accounts/holdings/transactions need no FK churn.
- 2026-07-14  Supabase Row Level Security is deliberately NOT the authorization boundary: we reach Postgres over a direct pooler connection rather than PostgREST, so RLS never runs. Authorization lives in the API layer, where every query is scoped to the account the token resolves to.
- 2026-07-14  The market-data routes (`/api/quote`, `/api/search`, `/api/stock`, candles) require a signed-in user too, even though they touch no account, because they spend our Finnhub and Twelve Data quota. `/health` is the only open endpoint.
- 2026-07-14  Accounts open themselves, funded, on first sign-in; `seed.py` is now a manual top-up for an existing account (`--email`) rather than the creator of a single demo user (with real auth there is no "the" account, and a seeded row nobody can sign in as is dead weight).
- 2026-07-12  Historical price candles come from Twelve Data, not Finnhub, because Finnhub's free tier no longer serves `/stock/candle` (returns 403); it sits behind the market client as a second provider, configured with `TWELVE_DATA_API_KEY` (optional, only the charts need it).
- 2026-07-12  Orders can be sized by dollar amount or share quantity, with fractional shares, to match modern beginner apps; the dollars↔shares conversion is computed server-side at the latest quote and shares round down to 6dp so a fill never overshoots the cash or amount.
- 2026-07-12  A minimal analysis layer (portfolio value, per-position and total P/L, weights) shipped in M1 so the dashboard's numbers come from code; the remaining operators (concentration, volatility, benchmark) and the tutor tools stay in M3.
- 2026-07-12  The M1 dashboard chart is an allocation donut (holdings + cash by weight); the portfolio value-over-time line is deferred to M2 alongside the S&P 500 benchmark, since both need a time series we do not yet store.
- 2026-07-10  Backend data layer is synchronous SQLAlchemy 2.0 + Alembic on the psycopg (v3) driver, not async (the app is low-concurrency and the sim/analysis layers are pure synchronous functions; sync is simpler to test and read, and FastAPI runs sync routes in a threadpool).
- 2026-07-10  Auth for M0 and M1 is a single seeded user with no real login; real auth (Supabase Auth) lands in M2 (keeps the early milestones focused on the trading loop and tutor before adding accounts and sessions).
- 2026-07-10  Data comes from Finnhub and we run our own simulation, instead of using Alpaca's paper-trading engine for execution (Alpaca paper accounts are one-per-login and do not fan out to a multi-user app cleanly; our own cash/holdings/transactions model is simpler and multi-user native).
