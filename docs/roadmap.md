# Roadmap and Progress Log

Build one milestone at a time, top to bottom. Do not scaffold everything up front. A
milestone is done only when it works end to end, not when the code is written. When a
milestone is done, check its boxes here and add a one-line note under "Progress log" so the
next session knows where things stand.

Status key: [ ] not started, [~] in progress, [x] done.

## M0. Scaffold and keys

- [ ] Create the repo structure: `web/`, `api/`, `docs/` (docs already exist).
- [ ] Scaffold the Next.js app in `web/` with pnpm (`pnpm create next-app`): App Router,
      TypeScript, Tailwind. This generates `pnpm-lock.yaml`. Set the `packageManager` field in
      `web/package.json` (e.g. `pnpm@10.x`) and add `prettier` (plus optional
      `eslint-config-prettier`) to devDependencies. App runs with a placeholder page.
- [ ] Set up the FastAPI app in `api/` with uv. Add runtime deps via
      `uv add fastapi 'uvicorn[standard]' ...` and run `uv sync` to generate `uv.lock` (dev tools
      are already in pyproject). App runs with a health check endpoint.
- [ ] Postgres connected. Migrations set up. Empty tables from the data model exist.
- [ ] `.env.example` created. Finnhub key and DB URL wired up locally.
- [ ] Tooling enforced in CI (uv + pnpm): `ruff` (lint + format) + `mypy` + `pytest` (api),
      `eslint` + `prettier` + `tsc` + build (web). GitHub Actions runs them on every push and PR.
      Config files provided: `.github/workflows/ci.yml`, `.pre-commit-config.yaml`,
      `api/pyproject.toml`, `api/.python-version`, `web/.prettierrc.json`. CI keys its caches off
      `api/uv.lock` and `web/pnpm-lock.yaml`, so those lockfiles must exist (the scaffold steps
      above generate them).
- [ ] README written: what it is, how to run it, a one-paragraph architecture summary, and a
      pointer to `docs/`.
- [ ] Confirm a single Finnhub quote call works end to end (backend fetches, frontend shows it).

Blockers to clear early: get a Finnhub API key, get a Postgres instance (local or hosted),
and get an LLM API key ready for M3.

## M1. Core trading loop (no AI yet)

- [ ] Fake account with a $100,000 starting balance.
- [ ] Ticker search and a stock page: price, simple chart, one-line company blurb.
- [ ] Buy (market order) fills at latest quote, debits cash, creates a holding.
- [ ] Sell (market order) credits cash, reduces/removes the holding.
- [ ] Portfolio dashboard: holdings, total value, cash, total gain/loss, one chart. This is
      the default landing screen.
- [ ] Transaction history.
- [ ] Reset button.
- [ ] Market client caching in place so we stay under the free tier.

Goal: the core loop feels real and good before adding anything else.

## M2. Education layer

- [ ] Jargon tooltips (P/E, market cap, dividend yield, volume, etc.).
- [ ] First-time contextual explainers for new concepts.
- [ ] Plain-language money framing across the UI ("you made $240", not just "up 2.4%").
- [ ] Benchmark line: portfolio vs S&P 500 over the same period. High priority.

## M3. AI tutor

- [ ] Analysis layer operators built and unit tested (value, P/L, weights, concentration,
      volatility, benchmark).
- [ ] Read-only tools wrapping the analysis layer.
- [ ] Tutor with the system prompt enforcing the two hard rules (code computes, LLM narrates;
      education not advice).
- [ ] Tutor UI with a visible disclaimer.
- [ ] Sanity check: the tutor never emits a number that did not come from a tool, and never
      recommends buying or selling a specific security.

## M4. Extras

- [ ] Limit orders (with the market-vs-limit teaching moment).
- [ ] Watchlists.
- [ ] Per-stock news feed.
- [ ] Historical "time machine" mode.
- [ ] Achievements and streaks.

## Progress log

- (nothing yet) add a dated one-liner here each time a milestone lands.
