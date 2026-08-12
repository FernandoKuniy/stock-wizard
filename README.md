# Stock Wizard

[![CI](https://github.com/FernandoKuniy/stock-wizard/actions/workflows/ci.yml/badge.svg)](https://github.com/FernandoKuniy/stock-wizard/actions/workflows/ci.yml)

A paper-trading web app that teaches first-time investors. You get a pile of fake cash, buy and
sell real stocks and ETFs at real market prices, and an AI tutor explains what's happening in
plain English. Real market data, pretend money, education first. A simulation for learning, not
financial advice.

## Live demo

<!-- TODO after deploy: replace the line below with the real URL. -->

_Deploying to Vercel + Render — live URL going here._

Signup is **invite-only**, so a public link isn't open to every passer-by and bot spending the
API bills. Want to try it? Reach out for a code. Running it locally skips the gate entirely (see
[Running it locally](#running-it-locally)).

## Screenshots

<!-- TODO after deploy: drop a GIF or a few PNGs here, saved under docs/screenshots/.
     Suggested shots: the Overview with the S&P 500 benchmark line, a stock page with the
     price chart and the "what if you'd invested" panel, and the AI tutor slide-over. -->

_Coming soon._ The [live demo](#live-demo) is the fastest look in the meantime.

## What it does

Sign up, get a funded $100,000 account, search a ticker, and land on a stock page with a live
price chart, a plain-English company blurb, and buy/sell by dollar amount or share quantity
(fractional shares included). The dashboard opens with the question that actually matters: your
money against the S&P 500, so you can see whether picking stocks beat just buying the whole
market. Jargon is one tap from a definition, short explainers appear the first time you meet a
new idea, and everything is framed in money ("you'd have $240 more") rather than naked percentages.

An AI tutor reads your real portfolio and explains it in plain English. The rule that keeps it
honest: **every number comes from code, and the tutor only ever explains figures the backend
already computed** — it can't invent a number or tell you to buy or sell anything.

There's more once the basics feel good: limit orders (introduced as a teaching moment),
watchlists, a per-stock news feed, a "what if you'd invested a year ago" time machine, habit
badges, a portfolio check-up, and a calm mode that hides the dollar figures when a red number is
the last thing a nervous beginner needs. See [docs/product-spec.md](docs/product-spec.md).

## Architecture

Two apps. `web/` is a Next.js (App Router) + TypeScript + Tailwind frontend. `api/` is a Python +
FastAPI backend on Postgres. The HTTP surface is thin: `api/main.py` is just the composition root,
and the routes live in `api/routers/`, one module per domain (stock, portfolio, orders, watchlist,
tutor, account). The real work sits in clear layers under `api/services/`:

- **`market/`** is the only thing that talks to the data providers (Finnhub for quotes, profiles,
  search, and news; Twelve Data for price candles) and the only place that caches them.
- **`sim/`** runs the paper-trading engine: cash, order fills, holdings, transactions.
- **`analysis/`** does the deterministic portfolio math — value, profit/loss, weights,
  concentration, volatility, the benchmark comparison. This is the source of truth for every figure.
- **`tutor/`** is the AI layer: an LLM with read-only, account-scoped tools, behind a swappable
  provider. It narrates; it never calculates.

One rule holds it together: numbers come from code, words come from the LLM. More in
[docs/architecture.md](docs/architecture.md).

## Running it locally

You need [uv](https://docs.astral.sh/uv/) for Python and [pnpm](https://pnpm.io/) for the
frontend. Never pip or npm.

### 1. Config

Both apps read a gitignored env file. Copy the examples and fill them in:

```bash
cp api/.env.example api/.env
cp web/.env.example web/.env.local
```

Backend (`api/.env`):

- `FINNHUB_API_KEY`: a free key from [finnhub.io](https://finnhub.io/).
- `DATABASE_URL`: a Postgres connection string. We use a Supabase session-mode pooler URL (a plain
  `postgresql://...`). Percent-encode any special characters in the password, or auth will fail.
- `SUPABASE_URL`: your project URL, e.g. `https://abcdefgh.supabase.co`. Not a secret: the API uses
  it to fetch the public keys it verifies access tokens with.
- `TWELVE_DATA_API_KEY`: optional, a free key from [twelvedata.com](https://twelvedata.com/). Only
  the price charts (and the sample-history seeding) need it; everything else works without it.
- `OPENAI_API_KEY`: optional, from [platform.openai.com](https://platform.openai.com/). Only the AI
  tutor needs it; without it the app runs fine and the tutor says it isn't set up. `TUTOR_MODEL`
  overrides the model (defaults to the cheapest current one).
- `SIGNUP_CODE`: optional, the invite gate. Leave it **unset locally** and signup is frictionless.
  Set it in a deployed environment and nobody gets an account (or any access) until they redeem it.
- `SEED_NEW_ACCOUNTS`: optional. Set it `true` (mainly for the hosted demo) to give every new
  account the six-month sample portfolio on sign-in, so a visitor lands on a dashboard that teaches
  instead of an empty one. Off by default.

Frontend (`web/.env.local`):

- `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, both from your project's API
  settings. Both are public and safe in the browser. Use the publishable key (`sb_publishable_...`),
  never the secret key.
- `NEXT_PUBLIC_API_URL`: defaults to `http://localhost:8000`.

Your Supabase project needs **JWT signing keys** enabled (asymmetric ES256 or RS256, the default for
new projects); the API rejects the legacy shared HS256 secret. For local development, turn off email
confirmation under Authentication → Sign In / Providers, or you'll have to click an email link before
you can sign in. And because we reach Postgres directly rather than through PostgREST, **turn the
Data API off** (or the tables are exposed) — see [Security](#security).

### 2. Database

Create (or update) the tables:

```bash
cd api && uv run alembic upgrade head
```

### 3. Backend

```bash
cd api && uv run uvicorn main:app --reload
```

Runs on `http://localhost:8000`. Health check at `/health`; everything else lives under `/api` and
needs a signed-in user.

### 4. Frontend

```bash
cd web && pnpm install && pnpm dev
```

Runs on `http://localhost:3000`. Create an account and you'll land on your dashboard with $100,000
of fake money. Accounts fund themselves on first sign-in.

A brand new account has a portfolio chart one day wide, which teaches nobody anything. To give
yours a real curve, backdate it six months and buy five well-known companies at the actual closing
price of the day it says it bought them:

```bash
cd api && uv run python -m seed --email you@example.com --history
```

The money is still fake and the prices are still real, which is the whole premise. Drop `--history`
to only fund the account. Hit **Reset account** in the app to wipe it and start over.

## Security

This is a simulation, but it holds real emails and per-user balances, so a few things are load-bearing:

- **Authorization lives in the API, not in the database.** We reach Postgres over a direct pooler
  connection, not through PostgREST, so Supabase Row Level Security never runs on our own queries.
  Every route scopes its reads to the signed-in account, and a test proves one user's money never
  appears in another's. RLS is still enabled deny-by-default, and the Supabase **Data API is turned
  off**, so the tables aren't exposed even if someone has the browser's publishable key.
- **Signup is invite-gated at the API.** A shared code is enforced where every route already funnels
  through, not just on the form, so it can't be bypassed by calling Supabase's signup endpoint directly.
- **The tutor can't make up numbers.** A provenance guard checks that every figure in a tutor reply
  traces back to a tool that computed it, and the tutor is rate-limited per account so a leaked code
  can't run up the OpenAI bill.

The reasoning behind each of these is in [docs/decisions.md](docs/decisions.md).

## Known limitations

Deliberate scope calls for a teaching demo, not oversights:

- **No corporate actions.** Stock splits and dividends aren't modeled, so a split would show a holder
  a distorted position until it works through. Fine over a demo's lifetime; real for a long-lived one.
- **Orders fill against the last price outside market hours.** A "market" order placed on a weekend
  fills at Friday's close. The app is a teaching tool, not a live execution venue.
- **Limit orders settle lazily.** There's no background job by design; a resting order is checked when
  you next load your portfolio or orders, not continuously. So an order may fill "late" if you don't
  come back for a while.
- **Provider free tiers set a ceiling.** Twelve Data allows 8 candle calls a minute, so an account
  holding more than ~7 distinct symbols can hit the limit on a cold cache. It degrades to a clear
  "couldn't load your history" rather than a wrong chart.
- **The rate limiter and market cache are in-process.** Fine for a single instance; a multi-instance
  deploy would want a shared store (Redis) instead.
- **Delisted or renamed tickers** in an old portfolio aren't specially handled.

## Development

- Backend tests: `cd api && uv run pytest`
- Lint/format (api): `uv run ruff check .` and `uv run ruff format .`
- Lint/format (web): `pnpm lint` and `pnpm exec prettier --write .`
- Type checks: `uv run mypy .` (api) and `pnpm exec tsc --noEmit` (web)
- Git hooks: `uv tool install pre-commit && pre-commit install`

CI runs all of these on every push and pull request.

## Docs

- [docs/product-spec.md](docs/product-spec.md): features, the education approach, UX.
- [docs/architecture.md](docs/architecture.md): data model, integrations, AI design, security.
- [docs/roadmap.md](docs/roadmap.md): the build plan and progress log.
- [docs/decisions.md](docs/decisions.md): decisions that diverge from the original plan.

## License

[MIT](LICENSE).
