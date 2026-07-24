# Roadmap and Progress Log

Build one milestone at a time, top to bottom. Do not scaffold everything up front. A
milestone is done only when it works end to end, not when the code is written. When a
milestone is done, check its boxes here and add a one-line note under "Progress log" so the
next session knows where things stand.

Status key: [ ] not started, [~] in progress, [x] done.

## M0. Scaffold and keys

- [x] Create the repo structure: `web/`, `api/`, `docs/` (docs already exist).
- [x] Scaffold the Next.js app in `web/` with pnpm (`pnpm create next-app`): App Router,
      TypeScript, Tailwind. This generates `pnpm-lock.yaml`. Set the `packageManager` field in
      `web/package.json` (e.g. `pnpm@10.x`) and add `prettier` (plus optional
      `eslint-config-prettier`) to devDependencies. App runs with a placeholder page.
- [x] Set up the FastAPI app in `api/` with uv. Add runtime deps via
      `uv add fastapi 'uvicorn[standard]' ...` and run `uv sync` to generate `uv.lock` (dev tools
      are already in pyproject). App runs with a health check endpoint.
- [x] Postgres connected. Migrations set up. Empty tables from the data model exist.
- [x] `.env.example` created. Finnhub key and DB URL wired up locally.
- [x] Tooling enforced in CI (uv + pnpm): `ruff` (lint + format) + `mypy` + `pytest` (api),
      `eslint` + `prettier` + `tsc` + build (web). GitHub Actions runs them on every push and PR.
      Config files provided: `.github/workflows/ci.yml`, `.pre-commit-config.yaml`,
      `api/pyproject.toml`, `api/.python-version`, `web/.prettierrc.json`. CI keys its caches off
      `api/uv.lock` and `web/pnpm-lock.yaml`, so those lockfiles must exist (the scaffold steps
      above generate them).
- [x] README written: what it is, how to run it, a one-paragraph architecture summary, and a
      pointer to `docs/`.
- [x] Confirm a single Finnhub quote call works end to end (backend fetches, frontend shows it).

Blockers to clear early: get a Finnhub API key, get a Postgres instance (local or hosted),
and get an LLM API key ready for M3.

## M1. Core trading loop (no AI yet)

- [x] Fake account with a $100,000 starting balance.
- [x] Ticker search and a stock page: price, simple chart (Twelve Data candles), one-line
      company blurb.
- [x] Buy (market order) fills at latest quote, debits cash, creates a holding. Sized by
      dollar amount or share quantity, fractional shares allowed.
- [x] Sell (market order) credits cash, reduces/removes the holding.
- [x] Portfolio dashboard: holdings, total value, cash, total gain/loss, one chart (an
      allocation donut). This is the default landing screen.
- [x] Transaction history.
- [x] Reset button.
- [x] Market client caching in place so we stay under the free tier.

Goal: the core loop feels real and good before adding anything else.

## M2a. Accounts and auth

Auth comes before the education layer so the rest of the UI is never built on the
single-seeded-user assumption. The docs always said auth lands in M2; this is that.

- [x] Supabase Auth (email + password): login screen, session refresh, sign out.
- [x] `users.auth_id` links a row to its Supabase Auth user; email is no longer the identity.
- [x] The API verifies access tokens locally against the project's JWKS (ES256).
- [x] Every route is scoped to the signed-in user's account, with a test proving two users
      cannot see each other's money. RLS does not cover these tables, so this layer is the
      only thing enforcing it (see architecture.md).
- [x] Accounts open themselves, funded, on first sign-in. `seed.py` becomes a manual top-up.

## M2b. Education layer

- [x] Backdated demo history (`seed --history`), so the benchmark line has a real curve to
      teach with, bought at real historical closing prices.
- [x] Benchmark line: portfolio vs S&P 500 over the same period, rebuilt from the
      transactions rather than stored as snapshots.
- [x] Jargon tooltips (market cap, cost basis, market order, S&P 500, and the rest).
- [x] First-time contextual explainers for new concepts (welcome, the benchmark, first order).
- [x] Plain-language money framing across the UI ("you made $240", not just "up 2.4%").
- [x] Fix: a failed quote silently dropped a holding from the portfolio totals, so one flaky
      Finnhub call read as a big fake loss. Now carried at cost and flagged as stale.

## M3. AI tutor

- [x] Analysis layer operators built and unit tested (value, P/L, weights, concentration,
      volatility, benchmark).
- [x] Read-only tools wrapping the analysis layer.
- [x] Tutor with the system prompt enforcing the two hard rules (code computes, LLM narrates;
      education not advice).
- [x] Tutor UI with a visible disclaimer.
- [x] Sanity check: the tutor never emits a number that did not come from a tool, and never
      recommends buying or selling a specific security.

## M4. Extras

- [x] Limit orders (with the market-vs-limit teaching moment).
- [x] Watchlists.
- [x] Per-stock news feed.
- [x] Historical "time machine" mode (shipped as a what-if calculator; see decisions.md).
- [x] Achievements and streaks (shipped as habit badges; teaching over retention, see
      decisions.md). **M4 complete.**

## M5. Layout and the second teaching pass

The dashboard split comes first, because most of the features below need somewhere to live
and adding them to the old single page would have made the chaos worse before it got better.

- [~] Split the dashboard into Overview / Holdings / Activity, with a three-item nav.
- [~] Dock the tutor so it's reachable from every page, not just the overview.
- [~] Period selector on the performance chart (1M / 6M / 1Y / All). No 1D or 1W: short
      windows are what make people trade.
- [~] Portfolio check-up: deterministic rules over the snapshot, each with a plain-English
      reason. Surfaces the concentration and sector math `analysis/risk.py` already computes.
- [~] "What moved your money": per-position P/L as a ranked sentence, not a table column.
- [ ] "What if you'd done nothing": the account against buy-and-hold of its own first buys.
- [ ] Monthly-investing comparison in the time machine (lump sum vs the same money spread out).
- [ ] "Why did it move?" news on a big daily change (product-spec has always listed this).
- [ ] Biggest daily moves of the last year, with that day's headline where we have one.
- [ ] Calm mode: hide the dollar amounts, keep the plain-English sentence.
- [ ] Glossary page over the terms we already define on both sides.
- [ ] Start-here path for a brand new account.
- [ ] Mobile and keyboard pass.

## Progress log

- 2026-07-22  M4 (achievements) code complete, the last extra, which **completes M4**. Shipped
  as habit badges rather than the "streaks to bring people back" the spec named: rewarding
  activity or profit in a trading app teaches the exact behaviour the benchmark chart warns
  against, so the goal was redefined from retention to teaching (see decisions.md). Six badges,
  all good habits: five companies at once, holding a position through 1/3/6/12 months (the only
  "streak", from data we already store, so no new column), and sitting through a 15%+ dip
  without selling. New pure `services/analysis/achievements.py` (a `continuous_hold_days` walk
  and an `evaluate` predicate over plain facts, plus the static badge copy) and a thin
  `services/achievements.py` awarding layer beside `portfolio.py`. Detection is lazy on `GET
  /api/portfolio` off the snapshot already in hand (no provider call, no cron, no new route),
  add-only and idempotent (unique on account+key), and it survives a reset. One new table
  (migration 0005). The tutor deliberately gets no achievements tool. 227 backend tests green
  (25 new: the hold-duration boundaries incl. sell-and-rebuy resetting the clock, every ladder
  threshold, the dip's time/percent/unpriced cases, awarding idempotency and add-only, plus
  account isolation and survive-reset through the API); ruff + mypy clean; web passes eslint +
  prettier + tsc and a production build. Browser click-through still pending a sign-in.
- 2026-07-15  M4 (time machine) code complete, the fourth extra, shipped as a what-if calculator
  rather than a replay mode (see decisions.md). A new pure `services/analysis/whatif.py` buys at
  the real close on the first trading day on or after the start date, values it at the latest
  close, and pairs the answer with the same money in the S&P 500 over the same window; the
  comparison is dropped rather than drawn if the index can't be priced over that exact window.
  `GET /api/stock/{symbol}/what-if` serves it through a `build_what_if` composer, capped at the
  cached two-year candle window so a what-if on a stock page normally costs no provider call.
  The stock page renders the default ($1,000, one year) with the page and refetches as the user
  changes the amount or period, and the copy is blunt that past moves say nothing about future
  ones. 202 backend tests green (18 new: gains, losses, closed-market start dates, exact
  fractional shares, a stock beating and trailing the index, a missing or too-short index, a
  symbol with no history that far back); ruff + mypy clean; web passes eslint + prettier + tsc
  and a production build. Browser check still pending a sign-in.
- 2026-07-15  M4 (per-stock news feed) done, verified end to end in the browser. The second
  extra, and the smallest: the Finnhub company-news fetch and its ten-minute cache already
  existed from M3, so this is a thin `GET /api/stock/{symbol}/news` route (signed-in, degrades
  to a 502 the page hides) plus a "Recent news" section on the stock page, showing up to six
  recent headlines with source and date, each linking out. Verified live against AMZN (six
  headlines, correct attribution, no console errors). 154 backend tests green (3 new: returns
  articles, needs a token, degrades on outage); ruff + mypy clean; web passes eslint + prettier
  + tsc.
- 2026-07-15  M4 (watchlists) code complete, first of the extras. A new `watchlist_items` table
  (account-scoped, unique on (account, symbol), migration 0003) plus three thin routes scoped
  through `get_current_account`: list (with a live quote per symbol that degrades to null one
  symbol at a time, like the dashboard's stale holdings), add (validated against a live quote so
  a junk ticker is never stored, idempotent), and delete (204, no-op if absent). The list
  endpoint takes `include_quotes=false` so the stock page's Watch star can check membership
  without spending quote quota on a ticker the user isn't viewing. UI: a Watch button on the
  stock page is the way to add, and the dashboard shows the list with a remove control and a
  first-time explainer, appearing only once something is watched. 149 backend tests green (8 new,
  covering add/list/remove, ordering, idempotency, unknown-symbol rejection, per-symbol quote
  degradation, the membership-only fetch, and account isolation); ruff + mypy clean; web passes
  eslint + prettier + tsc + a production build. Verified as far as the sign-in wall allows (routes
  wired and auth-gated, migration applied, all pages compile); the signed-in click-through is the
  one step left, since sign-in needs the user's credentials.
- 2026-07-15  M3 code complete (browser end-to-end pending an OpenAI key): the AI tutor. Finished
  the analysis layer (concentration/diversification signals and per-position volatility, both pure
  and unit-tested), added a Finnhub company-news fetch, and built `services/tutor/`: an OpenAI
  provider behind a swappable interface (`TutorProvider`, one `TutorError` contract, mocked in
  tests), six read-only tools scoped to the signed-in account (portfolio summary, position detail,
  concentration, benchmark comparison, recent news, explain a term), a tool-calling engine, and a
  system prompt that carries the two hard rules. Every figure the tutor states comes from a tool
  (deterministic code); a pure provenance guard proves it in tests and monitors it at runtime.
  Conversations are ephemeral (held in the browser, sent back each turn, no table). `/api/tutor` is
  scoped through `get_current_account`, and a dashboard chat panel carries the "simulation, not
  advice" disclaimer. Numbers stay identical to the dashboard by sharing `services/portfolio.py`
  (snapshot + history builders, which the `/api/portfolio` routes were refactored onto). 141
  backend tests green (plus one opt-in live check against the real model). The model is OpenAI's
  cheapest (`gpt-5.4-nano`, overridable via `TUTOR_MODEL`); the tutor stays disabled until
  `OPENAI_API_KEY` is set in `api/.env`, at which point it degrades to a clear "not set up" message.
- 2026-07-10  M0 complete: Next.js 16 web + FastAPI/uv api, sync SQLAlchemy 2.0 with Alembic
  migrations applied to Supabase (users, accounts, holdings, transactions), and a market client
  showing a live Finnhub quote on the home page. Tooling (ruff, mypy, pytest, eslint, prettier,
  tsc) is green locally. Single seeded user with no real login is the M0-M1 plan; Supabase Auth
  lands in M2.
- 2026-07-14  M2b complete: the education layer, verified end to end in the browser. The
  dashboard now leads with the portfolio against the S&P 500, rebuilt deterministically from
  the transactions and real closing prices (no snapshot table, no cron). `seed --history`
  backdates a demo account six months and buys five companies at real historical closes, so
  the chart teaches from the first screen. Plus jargon tooltips, first-time explainers
  (localStorage, no schema change), and a money-framing pass. Checked against live data: 128
  trading days, both lines starting at exactly $100,000, the demo portfolio up 6.43% against
  the index's 9.02%. Also fixed a dashboard bug where a failed quote dropped a holding from
  the totals and read as a large fake loss.

  Watch out in M3: drawing the history costs one Twelve Data call per symbol ever held, plus
  one for the index, against a free tier of 8 a minute. A wider portfolio will trip it. See
  the "Known ceiling" note in architecture.md.
- 2026-07-14  M2a complete: real auth, verified end to end in the browser (sign up -> funded
  dashboard -> buy). Supabase Auth (email + password) on the frontend, with session refresh in
  `proxy.ts` and a login screen; the API verifies access tokens locally against the project's
  ES256 JWKS and scopes every route to the signed-in user's account. Accounts open themselves,
  funded, on first sign-in, so there is nothing to seed. Note for anyone reading later:
  Supabase RLS does NOT protect these tables (we go straight to Postgres, not through
  PostgREST), so the API's account scoping is the only thing keeping users apart.
- 2026-07-12  M1 complete: the core trading loop works end to end. A seeded $100k demo account,
  ticker search and a stock page (Finnhub quote/profile, Twelve Data price chart), market
  buy/sell by dollars or shares with fractional fills, a portfolio dashboard (totals, gain/loss,
  allocation donut), transaction history, and reset. Numbers come from a new deterministic
  analysis layer; a minimal subset (value, P/L, weights) shipped now, the rest lands with the
  tutor in M3. Verified end to end against live Finnhub + Twelve Data.
