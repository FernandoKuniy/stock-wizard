# Stock Wizard

A paper-trading web app that teaches first-time investors. You get a pile of fake
cash, buy and sell real stocks and ETFs at real market prices, and an AI tutor
explains what's happening in plain English. Real market data, pretend money,
education first. It is a simulation for learning, not financial advice.

## Status

The core trading loop works end to end, and it's multi-user: sign up, get a funded $100k
account, search a ticker, land on a stock page with a live price chart, buy and sell by
dollar amount or share quantity (fractional shares included), watch a portfolio dashboard
with an allocation chart, read your transaction history, and reset the whole thing when you
want a do-over. The education layer (a benchmark line against the S&P 500, jargon tooltips)
is next, then the AI tutor. See [docs/roadmap.md](docs/roadmap.md) for the plan and progress.

## Architecture

Two apps. `web/` is a Next.js (App Router) + TypeScript + Tailwind frontend. `api/`
is a Python + FastAPI backend on Postgres. The backend splits into clear layers under
`api/services/`: `market/` is the only thing that talks to the data providers (Finnhub for
quotes, profiles, and search; Twelve Data for price candles) and caches them, `sim/` runs the
paper-trading engine, `analysis/` does the deterministic portfolio math, and `tutor/` will be
the AI layer. One rule holds it together: every number comes from code, and the LLM only ever
explains figures the code already computed. More in [docs/architecture.md](docs/architecture.md).

## Running it locally

You need [uv](https://docs.astral.sh/uv/) for Python and [pnpm](https://pnpm.io/) for
the frontend. Never pip or npm.

### 1. Config

Both apps read a gitignored env file. Copy the examples and fill them in:

```bash
cp api/.env.example api/.env
cp web/.env.example web/.env.local
```

Backend (`api/.env`):

- `FINNHUB_API_KEY`: a free key from [finnhub.io](https://finnhub.io/).
- `DATABASE_URL`: a Postgres connection string. We use a Supabase session-mode pooler
  URL (a plain `postgresql://...`). Percent-encode any special characters in the
  password, or auth will fail.
- `SUPABASE_URL`: your project URL, e.g. `https://abcdefgh.supabase.co`. Not a secret: the
  API uses it to fetch the public keys it verifies access tokens with.
- `TWELVE_DATA_API_KEY`: optional, a free key from [twelvedata.com](https://twelvedata.com/).
  Only the price charts need it; everything else works without it (Finnhub's free tier no
  longer serves historical candles).

Frontend (`web/.env.local`):

- `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, both from your
  project's API settings. Both are public and safe in the browser. Use the publishable key
  (`sb_publishable_...`), never the secret key.
- `NEXT_PUBLIC_API_URL`: defaults to http://localhost:8000.

Your Supabase project needs **JWT signing keys** enabled (asymmetric ES256 or RS256, the
default for new projects). The API rejects the legacy shared HS256 secret. For local
development you'll also want to turn off email confirmation under Authentication → Sign In /
Providers, or you'll have to click a link in an email before you can sign in.

### 2. Database

Create the tables:

```bash
cd api && uv run alembic upgrade head
```

### 3. Backend

```bash
cd api && uv run uvicorn main:app --reload
```

Runs on http://localhost:8000. Health check at `/health`; everything else lives under `/api`
and needs a signed-in user.

### 4. Frontend

```bash
cd web && pnpm install && pnpm dev
```

Runs on http://localhost:3000. Create an account on the login screen and you'll land on your
dashboard with $100,000 of fake money. Accounts fund themselves on first sign-in, so there is
nothing to seed. To top one up by hand later:

```bash
cd api && uv run python -m seed --email you@example.com
```

## Development

- Backend tests: `cd api && uv run pytest`
- Lint/format (api): `uv run ruff check .` and `uv run ruff format .`
- Lint/format (web): `pnpm lint` and `pnpm exec prettier --write .`
- Type checks: `uv run mypy .` (api) and `pnpm exec tsc --noEmit` (web)
- Git hooks: `uv tool install pre-commit && pre-commit install`

CI runs all of these on every push and pull request.

## Docs

- [docs/product-spec.md](docs/product-spec.md): features, the education approach, UX.
- [docs/architecture.md](docs/architecture.md): data model, integrations, AI design.
- [docs/roadmap.md](docs/roadmap.md): the build plan and progress log.
- [docs/decisions.md](docs/decisions.md): decisions that diverge from the original plan.
