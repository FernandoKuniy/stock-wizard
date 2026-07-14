# Architecture

## Stack rationale

- Python + FastAPI backend because the finance and AI ecosystem is Python-heavy, and the
  deterministic compute operators (the "numbers" layer) live naturally here.
- Next.js + TypeScript + Tailwind frontend for a fast, clean, modern UI.
- Postgres because the data is relational (users, accounts, holdings, transactions) and we
  want reliable balances.
- Recharts for charts. Simple and good enough for a beginner product. If you later want
  more "real" financial charts, TradingView Lightweight Charts is the upgrade path.

## Key decision: we run our own simulation, not a third-party paper engine

Alpaca offers a paper-trading environment that handles fills and tracks a paper account.
It is great, but a paper account is tied to one Alpaca login, so it does not map cleanly to
a multi-user web app where every user needs their own independent portfolio.

So the cleaner design for this app is:

- Use a market-data API (Finnhub) for prices, candles, company info, and news ONLY.
- Run our own tiny simulation in Postgres: cash balance, holdings, transactions.
- A market order for N shares at the current quote is a trivial, correct fill: check the
  latest price, check the user has enough cash, debit cash, add the position, log the trade.

This is exactly what the solid open-source references (CS50 Finance and friends) do. It is
simpler, fully multi-user, and gives us total control. If we ever go single-user or want
real order semantics, Alpaca paper is the fallback, but do not reach for it by default.

## Data model (starting point)

- `users`: id, auth_id (the Supabase Auth user id, unique), email, created_at.
- `accounts`: id, user_id, cash_balance, starting_balance, created_at. (One per user for
  now. The starting_balance lets us compute total return and power the reset.)
- `holdings`: id, account_id, symbol, quantity, avg_cost. (avg_cost drives per-position P/L.)
- `transactions`: id, account_id, symbol, side (buy/sell), quantity, price, timestamp.
- `watchlist_items` (later): id, account_id, symbol.

Reset = set cash_balance back to starting_balance, delete holdings and transactions for
that account.

## Backend data layer and identity

- Persistence is synchronous SQLAlchemy 2.0 with Alembic migrations, on the psycopg (v3)
  driver (`postgresql+psycopg`). `DATABASE_URL` is a Supabase session-mode pooler URL
  (a plain `postgresql://`); the driver is forced on in code, not in the env value. Sync
  rather than async because the app is low-concurrency and the sim/analysis layers are
  pure synchronous functions that are simplest to test and read that way. FastAPI runs
  sync route handlers in a threadpool, so DB calls do not block the event loop.
- Money is stored as `Numeric`/`Decimal`, never float, so balances stay exact. Figures cross
  the HTTP boundary as JSON numbers rounded for display (money to cents), while all math stays
  in `Decimal` server-side. The frontend only formats; it never recomputes a figure.
- The engine and a per-request `get_db` session dependency live in `db.py`; route handlers
  (and the sim) own the transaction boundary and commit explicitly. `seed.py` idempotently
  creates the single funded demo account (`uv run python -m seed`).
- Identity: users sign in with Supabase Auth (email and password). See "Auth" below.

## Auth

Supabase Auth owns sign-up, sign-in, and sessions. We own authorization.

- The frontend uses `@supabase/ssr`. `proxy.ts` (Next.js 16's rename of `middleware.ts`)
  refreshes the session on every request and bounces signed-out visitors to `/login`. It
  decides who someone is with `getClaims()`, which verifies the token's signature;
  `getSession()` does not, and is never trusted for that on the server.
- Every call to our API carries the user's access token as a bearer token. The token comes
  from a different place depending on where the code runs (server component vs browser), so
  `lib/api.ts` takes it as an argument instead of guessing at runtime.
- The API verifies the token itself, locally, against the project's public JWKS
  (`/auth/v1/.well-known/jwks.json`). Supabase signs with an asymmetric key (ES256), so the
  backend holds no shared secret and never calls Supabase to check a request. Only ES256 and
  RS256 are accepted: the legacy shared HS256 secret is rejected outright, so a leaked secret
  could not mint a token we would trust. Claims checked: signature, `exp`, `iss`, `aud`, `sub`.
- `users.auth_id` (the token's `sub`) is the real identity. `email` is a display copy and is
  no longer unique, since Supabase owns email uniqueness. Integer surrogate keys stay.
- Accounts open themselves: the first time someone signs in, `services/sim/accounts.py` gives
  them a user row and a funded account. `seed.py` is now just a manual top-up for an account
  that already exists (`uv run python -m seed --email you@example.com`).

**IMPORTANT: Supabase Row Level Security does not protect these tables.** We reach Postgres
over a direct connection (the session pooler), not through PostgREST, so RLS never runs.
Authorization lives entirely in the API layer: a request resolves to exactly one account, and
every query is scoped to it. If a route ever reads a table without scoping to
`get_current_account`, that is a data leak, and nothing in the database will stop it. A test
in `tests/test_api.py` holds the line by proving one user's trades never appear in another's
portfolio.

Everything under `/api` requires a token, including the market-data routes: they do not touch
an account, but they do spend our Finnhub and Twelve Data quota. `/health` is the only open
endpoint.

## Market data layer (`services/market/`)

All external data calls and all caching live here. Nothing else touches a provider.

- Quotes: current price for a symbol, from Finnhub. Cache with a short TTL (a few seconds to a
  minute is fine for an educational app, and the free tier is delayed anyway).
- Candles: historical daily bars for charts, from Twelve Data. Finnhub's free tier no longer
  serves `/stock/candle` (it 403s), so a second provider sits behind the market client for
  candles; it uses `TWELVE_DATA_API_KEY` (optional, only charts need it). Cache longer (past
  days do not change intraday).
- Company profile and symbol search: from Finnhub. The profile drives a plain-language,
  code-composed "what is this company" blurb (no LLM). Cache profiles for a long time.
- News: recent articles per symbol (later). Cache for minutes.

Both providers sit behind one `MarketError` contract, so no raw provider error reaches the
user and swapping a provider stays a market-layer change.

Caching rules that keep us under the free tier:

- Only fetch a quote when a user is actually viewing that symbol or holds it and is on the
  portfolio screen. Never poll the whole universe.
- Batch and dedupe. If ten things need AAPL's price in the same tick, make one call.
- Cache aggressively per the TTLs above. Free tiers die from sloppy loops, not real load.

## Simulation layer (`services/sim/`)

The paper-trading engine. Pure, testable functions over the database session:

- `buy(session, account, symbol, *, quantity | amount, market)`: get the latest quote; size the
  order by share `quantity` or dollar `amount` (shares = amount / price, computed here in code);
  verify cash; debit cash; upsert the holding (recompute the weighted avg_cost); write a
  transaction.
- `sell(session, account, symbol, *, quantity | amount, market)`: verify shares held, credit
  cash, reduce or remove the holding, write a transaction. A dollar-sized sell caps at the
  position.
- `reset(session, account)`: restore the starting balance, clear holdings and transactions.

Shares are held to 6 decimals and always round down, so a fill never spends more than the cash
or dollar amount asked; money is quantized to 4 decimals. Failures are typed `SimError`s
(insufficient funds/shares, invalid order) with user-safe messages. The functions flush but do
not commit, so the caller owns the transaction boundary. Keep this layer free of HTTP and
framework code so it is easy to unit test.

## Analysis layer (`services/analysis/`) — the "numbers"

This is the source of truth for every figure the UI or the AI shows. All deterministic
Python. No LLM anywhere near it.

The M1 subset is built and unit-tested (portfolio value, per-position and total profit/loss,
position weights), so the dashboard's numbers come from code. The rest lands in M3 with the
tutor.

Operators:

- Total portfolio value = cash + sum(quantity * current price).
- Total and per-position profit/loss, absolute and percent.
- Position weights (each holding as a percent of the portfolio).
- Concentration and diversification signals (e.g. top holding weight, number of positions,
  sector spread using Finnhub sector data).
- Simple volatility from historical candles.
- Benchmark comparison vs SPY over the same period.

Every function takes plain data in and returns plain numbers out, with clear names so the
tutor can reference them by name.

## AI tutor layer (`services/tutor/`) — the "words"

An LLM with read-only tool-calling. The tools are thin wrappers over the analysis layer, so
the model can ask for figures but can never compute them itself.

- Tools (all read-only): get_portfolio_summary, get_position_detail, get_concentration,
  get_benchmark_comparison, get_recent_news, explain_term. Each returns code-computed data.
- System prompt encodes the two hard rules from CLAUDE.md: numbers come from the tools not
  the model, and this is education not advice. It teaches, explains tradeoffs, and answers
  "what does this mean for me" using the user's real figures. It never says buy or sell a
  specific security.
- Keep a short disclaimer visible in the tutor UI.
- Provenance: when the tutor cites a number, it should be a number a tool returned.

The `open-paper-trading-mcp` repo is a working reference for the read-only-tools-over-a-
portfolio pattern if you want to see one built out. FinRobot is the reference for the
strict "code computes, LLM narrates" separation.

Model choice is swappable. Start with whatever you have easy API access to and keep the
tutor behind an interface so the provider is not baked in.

## Secrets and config

- `FINNHUB_API_KEY`, `DATABASE_URL`, and the LLM API key live in `api/.env`, gitignored.
- `SUPABASE_URL` (api) and `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`
  (web) are public, not secrets: they locate the project and let a caller start an auth flow.
  The publishable key is safe in the browser. The secret key never goes near the frontend.
- Provide a `.env.example` in both `api/` and `web/` with the variable names and no values.

## Testing approach

- Unit test the sim and analysis layers hard. They are pure functions and they are where
  correctness matters most (real balances, real math).
- Mock the market client in tests so tests do not hit Finnhub or burn quota.
