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
- `orders`: id, account_id, symbol, side, quantity, limit_price, status
  (open/filled/cancelled), created_at, resolved_at, transaction_id, cancel_reason. Limit
  orders waiting for their price. `transaction_id` links a filled one to the trade it
  became, and `cancel_reason` records why we cancelled one on the user's behalf. Added in M4.
- `watchlist_items`: id, account_id, symbol, created_at, with a unique constraint on
  (account_id, symbol). Symbols the account is tracking without owning. No money columns:
  a watchlist is just a list of tickers. Added in M4.
- `achievements`: id, account_id, key, earned_at, with a unique constraint on (account_id,
  key). One row per badge an account has earned. The unique constraint makes awarding
  idempotent, so the lazy re-check on every dashboard load only writes the first time. Add-only
  (a badge is never removed) and it survives a reset, since it's a learning record, not money.
  Added in M4.

Reset = set cash_balance back to starting_balance, delete holdings and transactions for
that account. The watchlist and the achievements deliberately survive: neither is money, and
a badge is a record of something you once did, which a reset doesn't undo.

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
  candles; it uses `TWELVE_DATA_API_KEY` (optional, only charts need it). We always fetch the
  long window (about two years) and slice it, because a call costs the same whether it returns
  90 rows or 500. One fetch per symbol then serves both the stock page's price chart and the
  portfolio history. Cached for 6 hours, since daily bars only change once a day after the
  close.

  Known ceiling: drawing the portfolio history needs one call per symbol ever held, plus one
  for the index. Twelve Data's free tier allows 8 calls a minute, so an account holding more
  than about seven different symbols can hit the rate limit on a cold cache. It degrades
  cleanly (a clear "couldn't load your history" rather than a wrong chart), but it is a real
  limit to be aware of before anyone widens the demo portfolio.
- Company profile and symbol search: from Finnhub. The profile drives a plain-language,
  code-composed "what is this company" blurb (no LLM). Cache profiles for a long time.
- News: recent articles per symbol (a handful from the last week), from Finnhub's
  company-news endpoint, cached for ten minutes. Two things read it, both fetching only a
  symbol the user is actually looking at, so it stays well under the 60/min tier: the tutor's
  `get_recent_news` tool answers "why did this move?", and the stock page's `GET
  /api/stock/{symbol}/news` route (M4) feeds a "Recent news" section. Each headline links out
  and is attributed to its source; the numbers inside a headline are the source's words, not
  our computed figures.

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
- `reset(session, account)`: restore the starting balance, clear holdings, orders, and
  transactions. Orders go first, since a filled one points at the trade it became. The
  watchlist and the achievements deliberately survive a reset: the first is a list of things
  to look at, and the second is a learning record, neither of which is money.
- `fill_buy` / `fill_sell(session, account, symbol, shares, price)`: the settlement
  primitives. Given shares and a price they move the cash, update the holding, and write the
  transaction. Everything that can fill an order goes through them (market orders, the seed
  backfill, and the limit sweep), so the money math lives in one place and cannot drift.

Shares are held to 6 decimals and always round down, so a fill never spends more than the cash
or dollar amount asked; money is quantized to 4 decimals. Failures are typed `SimError`s
(insufficient funds/shares, invalid order) with user-safe messages. The functions flush but do
not commit, so the caller owns the transaction boundary. Keep this layer free of HTTP and
framework code so it is easy to unit test.

### Limit orders and the lazy fill (`services/sim/orders.py`, M4)

A limit order names a price and waits. This app deliberately runs no background job, so an
order cannot be watched continuously; it is checked **lazily**, whenever the user loads their
portfolio (`GET /api/portfolio`) or their orders (`GET /api/orders`). `sweep` takes every open
order on the account, fetches a fresh quote per symbol, and settles the ones whose price has
been reached. A buy crosses when the quote is at or below its limit, a sell at or above.

The rules, which the UI states plainly rather than hiding:

- **Fills happen at the limit price**, not at the quote we happened to see. The price passed
  through the limit on its way, so that is where the order would really have executed;
  filling at a later snapshot would pretend the user timed the move. It is also the
  conservative choice: a fill is never better than what they asked for.
- **Nothing is reserved at placement.** Cash moves only at fill, which keeps every existing
  money figure (the snapshot, the totals, the analysis layer) completely untouched. An
  account can therefore rest more buys than it can afford, and the first one to cross wins;
  the sweep works oldest-first so the order that waited longest gets the cash. If the money
  or the position is gone by the time the price arrives, the order is **cancelled with a
  reason** rather than part-filled, and the UI explains why.
- Orders are **good until cancelled** and fill **all or nothing**. There is no expiry and no
  partial fill, both of which would be real scope for no teaching gain.
- A symbol whose quote we cannot get is **skipped, never filled** — the same instinct that
  makes the history refuse to draw a line it cannot price.
- Placing a limit order costs no quote quota, since nothing is priced until it fills. A sell
  is checked against the position up front (this sim has no shorting), while a buy is not
  checked against cash, because the user may well fund it before the price arrives.

A fill writes an ordinary `Transaction`, so the portfolio history picks limit fills up for
free. The sweep locks the open rows for the transaction, so two concurrent loads cannot fill
the same order twice and spend the cash twice.

## Analysis layer (`services/analysis/`) — the "numbers"

This is the source of truth for every figure the UI or the AI shows. All deterministic
Python. No LLM anywhere near it.

Built and unit-tested, in `portfolio.py`, `history.py`, `risk.py`, and `whatif.py`:

- Total portfolio value = cash + sum(quantity * current price).
- Total and per-position profit/loss, absolute and percent.
- Position weights (each holding as a percent of the portfolio).
- Portfolio value over time, and the benchmark comparison vs SPY (see below).
- Concentration and diversification signals (`risk.py`): number of positions, the biggest
  holding's weight, an "effective number of holdings" from the Herfindahl index (how many
  equally sized bets the portfolio behaves like), and a sector breakdown from Finnhub's
  industry field. Measured across the holdings, with cash reported separately.
- Simple volatility (`risk.py`): the annualized standard deviation of a symbol's daily
  returns from its candles.
- The time machine (`whatif.py`, M4): what one lump sum into a stock on a past date would be
  worth at the latest close, always alongside the same money in the index over the same
  window. See below.

Every function takes plain data in and returns plain numbers out, with clear names so the
tutor can reference them by name. Composing an account's rows plus live market data into these
figures (fetching quotes, valuing unpriced holdings at cost, rebuilding the history series)
lives one level up, in `services/portfolio.py`, which both the dashboard routes and the tutor
tools call so their numbers are identical.

### Portfolio history and the benchmark (`history.py`)

We do NOT store daily snapshots of what an account was worth. The series is rebuilt on demand
from the transactions plus the real closing price of every symbol on every day. Replaying
those forward gives an exact value per day, it works from an account's first day rather than
only from the day we started recording, it survives a reset, and it needs no history table and
no cron job to keep one fed.

The benchmark takes the same starting balance, puts all of it into SPY on the day the account
opened, and holds. Both lines therefore start at exactly the starting balance, which is what
makes the comparison honest. The index's own trading days are the date spine, since it trades
whenever the US market is open; a symbol with no bar on a given day is carried at its last
close.

The two failure modes get deliberately opposite treatment:

- **The index is unavailable**: still draw the user's own line. It is correct on its own; we
  just cannot compare.
- **A held symbol's history is unavailable**: refuse to draw anything (502). A chart that
  quietly omits a position understates someone's money, and a wrong chart about your money is
  worse than no chart.

The same principle applies on the dashboard: a holding whose live quote fails is carried in
the totals at what it cost and flagged in `unpriced_symbols`, rather than dropped. Dropping it
would shrink the portfolio by the whole position, so one flaky Finnhub call would read as a
large loss the user never took.

### The time machine (`whatif.py`, M4)

"What if I'd put $1,000 into this a year ago?" Buys at the real close on the first trading
day on or after the start date (rolling forward over weekends and holidays, the same
convention the history spine uses), values it at the latest close, and returns the shares,
the value now, and the gain or loss. `GET /api/stock/{symbol}/what-if?amount=&period=` serves
it, composed by `build_what_if` in `services/portfolio.py` like the other builders.

Two things are deliberate:

- **It always shows the index alongside.** On its own, "you'd have made $500" is the kind of
  figure that reads as a nudge to buy, which is exactly what hard rule #2 forbids. Next to
  the S&P 500 over the same window it becomes the lesson the product is built around, and it
  just as often shows the single stock trailing the market. If the index can't be priced over
  the *same* window, the comparison is dropped rather than drawn across mismatched periods.
- **The lookback is capped at two years**, which is the candle window we already fetch and
  cache. On a stock page the chart has just loaded those same candles, so a what-if normally
  costs no provider call at all. Reaching further back would mean a second, longer fetch per
  symbol and real pressure on Twelve Data's 8-calls-a-minute tier.

Shares stay exact fractions here rather than rounding down to 6dp the way a real fill does:
this is a hypothetical, not an order, so rounding would only invent a loss the user never
took. A symbol with no history that far back returns 404 rather than a guess.

## AI tutor layer (`services/tutor/`) — the "words"

An LLM with read-only tool-calling. The tools are thin wrappers over the analysis layer, so
the model can ask for figures but can never compute them itself. Built in M3.

- **Provider (`provider.py`)**: the model sits behind a `TutorProvider` interface, the same
  pattern as the market client (a Protocol for the slice we use, one `TutorError` contract, an
  `lru_cache` factory, mocked in tests). The concrete provider wraps OpenAI's chat completions
  with tool calling; the engine only ever sees neutral message/tool types, so swapping the
  model or the whole provider is a change inside this one file. Model choice is a config value
  (`TUTOR_MODEL`, defaulting to OpenAI's cheapest), never baked into the code.
- **Tools (`tools.py`, all read-only)**: get_portfolio_summary, get_position_detail,
  get_concentration, get_benchmark_comparison, get_recent_news, explain_term. Each is bound to
  one account and reads only that account's money (the same `get_current_account` scoping every
  route uses), and returns code-computed figures via the analysis layer and the shared
  `services/portfolio.py` builders. `explain_term` reads a small server-side glossary that
  mirrors the frontend one.
- **Engine (`engine.py`)**: offers the model the tools, runs any it calls, feeds the results
  back, and repeats until it answers in prose, with a hard cap on tool rounds.
- **System prompt (`prompt.py`)** encodes the two hard rules from CLAUDE.md: numbers come from
  the tools not the model, and this is education not advice. It never says buy or sell a
  specific security.
- **Provenance guard (`guard.py`)**: a pure function that, given the answer and everything the
  tools returned, flags any number the tutor stated that no tool produced (allowing for the
  model rounding a figure for display). It is the enforceable form of hard rule #1: the tests
  assert it holds over controlled tool output, and at runtime it logs violations rather than
  mangling wording (the tools plus the prompt are the enforcement; the guard watches it hold).
- **UI**: a slide-over chat panel, opened from a button in the header, so the tutor is one
  click away from every page rather than living at the bottom of one of them. It keeps a short
  "simulation, not financial advice" disclaimer visible. The conversation is ephemeral: the
  thread lives in the browser and is sent back each turn, so nothing is stored server-side (no
  table, matching the stateless completion API). The panel is mounted in the root layout, which
  persists across navigation, so the thread survives moving between pages and is lost only on a
  full reload, which is the same ephemerality as before.

The `open-paper-trading-mcp` repo is a working reference for the read-only-tools-over-a-
portfolio pattern if you want to see one built out. FinRobot is the reference for the
strict "code computes, LLM narrates" separation.

## Watchlists (M4)

Symbols the user is tracking without owning. No money is involved, so this is deliberately
simple: account-scoped CRUD over `watchlist_items`, with no analysis or sim layer in the
path. Three routes, all scoped to `get_current_account` like every other account route (the
only thing keeping one user's list out of another's):

- `GET /api/watchlist` returns the account's symbols, each with a live quote (price and day
  change). A symbol whose quote fails is still returned, with null price fields, so one
  flaky quote never hides the rest of the list, exactly the degradation holdings get on the
  dashboard. An `include_quotes=false` query param skips the quotes and returns symbols
  only: the stock page's star uses it to learn whether a symbol is watched without spending
  quote quota on a ticker the user isn't actually looking at (the "only fetch what a user is
  viewing" rule).
- `POST /api/watchlist` validates the symbol against a live quote before storing it, so a
  ticker that doesn't resolve is never saved, and hands that quote back. Adding a symbol
  already on the list is a no-op, enforced by the unique constraint.
- `DELETE /api/watchlist/{symbol}` removes one (a no-op if it isn't there), returning 204.

In the UI, adding happens on the stock page (a Watch button), and the dashboard shows the
list with a live price and a remove control. The list section only appears once the account
has watched something; the ever-present Watch button is the way in.

## Achievements (M4)

Light gamification, aimed at teaching rather than retention. The whole design follows from
one decision (see decisions.md, 2026-07-22): rewarding activity (trades placed, days visited)
or outcomes (beating the market, big profits) would push a beginner toward exactly the
overtrading and outcome-chasing the benchmark chart exists to warn against. So every badge is
a **good habit whose finance is settled**, and most can only be earned once, so none creates
ongoing pressure. The set is six badges: holding five companies at once (diversification),
holding a single position through 1 / 3 / 6 / 12 months (the only "streak" that lines up with
good outcomes), and sitting through a 15%+ drop on a position held a month without selling.

This is hard rule #1 applied to a teaching feature, split across the usual two layers:

- **The fact is computed in `services/analysis/achievements.py`** (pure, no DB, no market).
  `evaluate(AccountFacts)` returns the set of earned keys from plain facts (position count,
  each position's continuous hold in days, each position's gain/loss). `continuous_hold_days`
  is the one piece of real logic: it walks a symbol's fills and measures the current unbroken
  hold, so selling out and re-buying resets the clock. The badge copy (`CATALOG`) is static,
  written by a person; the model never decides who earned what or writes a word of it.
- **The awarding is a thin composition step in `services/achievements.py`**, beside
  `portfolio.py`. It builds the facts from the account's transactions (for hold duration) and
  the already-built snapshot (for gain/loss), runs `evaluate`, and inserts any newly-earned
  rows. It reads no market data of its own, so awarding costs no provider call.

Detection is **lazy and no-cron**, the same shape as the limit-order sweep: badges are checked
inside `GET /api/portfolio`, off the snapshot already in hand, and committed only when a badge
is actually earned (a steady-state load stays a pure read). The result rides along on the
portfolio payload rather than adding a route. Awarding is **add-only and idempotent**: the
unique constraint on (account_id, key) means a re-check writes nothing once earned, and a
badge is never revoked, so selling a stock you held for a year doesn't undo the badge and a
reset leaves it standing. The dip badge only catches drops **below cost basis** (a stock that
ran up then fell back is missed); catching a true peak-to-trough drawdown would need a second
candle fetch per symbol, which isn't worth the pressure on Twelve Data's tier. The AI tutor is
deliberately **not** given an achievements tool this milestone: a congratulating tutor drifts
toward endorsement faster than a static badge does, for no teaching gain.

In the UI, a dashboard "Good habits" section lists earned and still-locked badges; each opens
its explainer with a native `<details>` (no client JS), and a locked badge shows how to earn
it. There is no streak counter and no nudging, on purpose.

## Secrets and config

- `FINNHUB_API_KEY`, `DATABASE_URL`, and `OPENAI_API_KEY` (the tutor's LLM) live in `api/.env`,
  gitignored. `OPENAI_API_KEY` is optional: without it the app still runs and the tutor endpoint
  reports that it isn't set up. `TUTOR_MODEL` optionally overrides the tutor's model.
- `SUPABASE_URL` (api) and `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`
  (web) are public, not secrets: they locate the project and let a caller start an auth flow.
  The publishable key is safe in the browser. The secret key never goes near the frontend.
- Provide a `.env.example` in both `api/` and `web/` with the variable names and no values.

## Testing approach

- Unit test the sim and analysis layers hard. They are pure functions and they are where
  correctness matters most (real balances, real math).
- Mock the market client in tests so tests do not hit Finnhub or burn quota.
