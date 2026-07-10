# Stock Wizard

A paper-trading web app that teaches first-time investors. You get a pile of fake
cash, buy and sell real stocks and ETFs at real market prices, and an AI tutor
explains what's happening in plain English. Real market data, pretend money,
education first. It is a simulation for learning, not financial advice.

## Status

M0 (scaffold and keys) is in place: both apps run, the database schema is defined as
Alembic migrations, and a live Finnhub quote flows end to end from the market API
through the backend to the home page. The trading loop and the AI tutor come next.
See [docs/roadmap.md](docs/roadmap.md) for the plan and progress.

## Architecture

Two apps. `web/` is a Next.js (App Router) + TypeScript + Tailwind frontend. `api/`
is a Python + FastAPI backend on Postgres. The backend splits into clear layers under
`api/services/`: `market/` is the only thing that talks to Finnhub (and caches it),
`sim/` runs the paper-trading engine, `analysis/` does the deterministic portfolio
math, and `tutor/` is the AI layer. One rule holds it together: every number comes
from code, and the LLM only ever explains figures the code already computed. More in
[docs/architecture.md](docs/architecture.md).

## Running it locally

You need [uv](https://docs.astral.sh/uv/) for Python and [pnpm](https://pnpm.io/) for
the frontend. Never pip or npm.

### 1. Secrets

The backend reads `api/.env` (gitignored). Copy the example and fill it in:

```bash
cp api/.env.example api/.env
```

- `FINNHUB_API_KEY`: a free key from [finnhub.io](https://finnhub.io/).
- `DATABASE_URL`: a Postgres connection string. We use a Supabase session-mode pooler
  URL (a plain `postgresql://...`). Percent-encode any special characters in the
  password, or auth will fail.

### 2. Database

Create the tables:

```bash
cd api && uv run alembic upgrade head
```

### 3. Backend

```bash
cd api && uv run uvicorn main:app --reload
```

Runs on http://localhost:8000. Health check at `/health`, quotes at `/api/quote/AAPL`.

### 4. Frontend

```bash
cd web && pnpm install && pnpm dev
```

Runs on http://localhost:3000. It reads `NEXT_PUBLIC_API_URL` (defaults to
http://localhost:8000); see `web/.env.example`.

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
