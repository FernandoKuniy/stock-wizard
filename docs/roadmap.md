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

- [x] Split the dashboard into Overview / Holdings / Activity, with a three-item nav.
- [x] Dock the tutor so it's reachable from every page, not just the overview.
- [x] Period selector on the performance chart (1M / 6M / 1Y / All). No 1D or 1W: short
      windows are what make people trade.
- [x] Portfolio check-up: deterministic rules over the snapshot, each with a plain-English
      reason. Surfaces the concentration and sector math `analysis/risk.py` already computes.
- [x] "What moved your money": per-position P/L as a ranked sentence, not a table column.
- [x] "What if you'd done nothing": the account against buy-and-hold of its own first buys.
- [x] Monthly-investing comparison in the time machine (lump sum vs the same money spread out).
- [x] "Why did it move?" news on a big daily change (product-spec has always listed this).
- [x] Biggest daily moves of the last year, with that day's headline where we have one.
- [x] Calm mode: hide the dollar amounts, keep the plain-English sentence.
- [x] Glossary page over the terms we already define on both sides.
- [x] Start-here path for a brand new account.
- [x] Mobile and keyboard pass. **M5 code complete**

## M6. Ship it as a portfolio demo

M5 finished the product. M6 doesn't add features; it makes the app something you can hand to a
recruiter: deployed, cheap and safe to leave running, and a repo that reads well on the first
click. Security first, then the demo experience, then repo polish, then deploy. What we leave
out matters as much as what we build (see non-goals).

Done already (the pre-launch hardening that kicked this off):

- [x] Enable RLS on every table and turn off the public Supabase Data API, closing a live leak
      that served every row to anyone with the browser publishable key.
- [x] Gate signup behind a shared invite code, enforced at the API, so a public URL isn't open
      to every passer-by and bot spending our AI and market-data quota.
- [x] Manually verify the signed-in click-through (sign in, search, buy, see it on the
      overview), the step pending since M3.

Safety and cost:

- [ ] Set a hard OpenAI spend cap at the billing level (dashboard, manual), so a runaway can't
      run up an unbounded bill.
- [ ] A light per-account throttle on the tutor endpoint, so one account (or a leaked invite
      code) can't loop the tutor and drive up the OpenAI bill.

The demo experience:

- [ ] Auto-seed every new account with the backdated six-month sample portfolio (`seed --history`
      logic wired into account creation), so the benchmark line, what-if, check-up and never-sold
      all teach from the first screen. Carry a clear "this is a sample, hit reset to start your
      own" banner; reset reveals the empty-state "start here" onboarding from M5. Watch Twelve
      Data quota: seeding buys five symbols at historical closes.
- [ ] Error boundaries: `error.tsx`, `not-found.tsx`, `loading.tsx` in the app's calm tone, so a
      prod hiccup never shows Next's default crash screen.
- [ ] A "simulation, not advice" line in the footer on every page.

Repo polish (the code is the deliverable):

- [ ] Split `main.py` (about 30KB, 20 routes) into `APIRouter`s by domain (stock, portfolio,
      orders, watchlist, tutor, account). Pure refactor, no behaviour change, covered by the
      existing tests.
- [ ] README as a landing page: the live URL and how to get in, screenshots or a short GIF, the
      architecture summary, a "Known limitations" section, and a "Security" note pointing at the
      decision log.
- [ ] A LICENSE file.
- [ ] Write "Known limitations" honestly rather than building around it: no stock-split or
      dividend handling, market orders fill at the last close outside market hours, limit orders
      sweep on page load. Deliberate scope calls, and saying so shows judgement.

Deploy (Vercel for `web/`, Render for `api/`):

- [ ] Set every env var in both hosts, including `SIGNUP_CODE` on Render and the Twelve Data key
      (the auto-seed needs it).
- [ ] Point Supabase Auth's Site URL and redirect URLs at the deployed domain, or confirmation
      and reset emails link to localhost.
- [ ] Allow the deployed Vercel origin through CORS (a single localhost origin today).
- [ ] Run `alembic upgrade head` as a Render pre-deploy step.
- [ ] Keep-warm: a scheduled ping so the free Supabase project doesn't pause after 7 days idle
      and the api isn't cold on every visit.
- [ ] Smoke-test a real invite signup on the deployed environment end to end.

Explicit non-goals for this milestone (a portfolio demo, not a public product):

- Custom SMTP for email deliverability (invite-only, low volume).
- Legal pages (terms, privacy) beyond the footer disclaimer.
- Account deletion and data export.
- Rate-limiting infrastructure like Redis; the invite gate plus the spend cap and light throttle
  are enough.
- Error tracking (Sentry) and a password-reset flow: considered and deferred, not worth the setup
  for an invite-only demo.

## M7. Dividends

Companies pay you to hold their stock. This was the biggest teaching gap: it rewards the same
patience the badges already teach, and it makes money show up in the account for doing nothing.

- [x] Dividend data behind a swappable provider in `services/market/`. No free tier serves it
      (Finnhub's is premium, Twelve Data's needs the paid Grow plan), so a curated, checked-in
      calendar covers the demo symbols; the provider is a drop-in swap for a live feed later.
- [x] `dividend_payments` table (migration 0008, RLS on). A cash event of its own, not a
      transaction, unique on (account, symbol, ex_date) so it's paid exactly once.
- [x] Lazy settlement on dashboard load, like the order sweep: pays for shares held before the
      ex-date, reconstructed from the transaction ledger. Idempotent, cleared by a reset.
- [x] Folded into the performance history so the line's last point matches the dashboard total,
      and into the benchmark (the S&P line now accrues its own dividends) so the comparison stays
      an honest total-return one rather than flattering the dividend collector.
- [x] `dividend_income` on the portfolio payload and a `/api/dividends` ledger. UI: a "companies
      have paid you $X" line on the overview, a dividends section on Activity, first-time
      explainers, and `dividend` / `ex-dividend date` glossary terms.

## M8. Recurring investing (dollar-cost averaging, by doing)

The habit the app most wants to teach, made real: automate a fixed buy on a schedule.

- [x] `recurring_investments` table (migration 0009, RLS on): amount, cadence, next/last run,
      active + paused_reason. Weekly/monthly only (no daily; that teaches noise-watching).
- [x] Lazy sweep on dashboard load through the same `buy`/`fill_buy` as a manual order. One run
      per load, then realign to the next future date, so a long gap fires once rather than
      stacking a pile of identical same-price buys. A run the account can't afford pauses with a
      reason instead of overdrawing; the user can resume it.
- [x] CRUD routes: create (validates the symbol against a live quote), list, pause/resume
      (PATCH), cancel (DELETE). Cleared by a reset like the orders.
- [x] UI: an "Invest automatically" card on the stock page and an "Automatic investing" section
      on Activity with pause/resume/cancel. Ties to the DCA what-if and glossary term; the
      what-if keeps the price-averaging lesson, this feature is the habit.

## M9. Realized vs unrealized

Beginners conflate a gain "on paper" with money they've actually made. This splits the account's
total gain into where it came from, so they can tell the difference.

- [x] Pure `services/analysis/realized.py`: replays the ledger with the same average-cost method
      the sim uses and books a realized gain on every sell. No new table, no provider call.
- [x] `build_returns` composer (shared by the route and the tutor) splits the total into realized
      + unrealized + dividends, which reconcile to `total_gain_loss` by construction.
- [x] `realized_gain` / `unrealized_gain` on the portfolio payload (rides along, no extra cost),
      a `get_returns_breakdown` tutor tool, a "Where your gain comes from" card on Holdings, and
      `realized gain` / `unrealized gain` glossary terms. Framed as understanding, never a verdict.

## M10. Tutor streaming

- [ ] Stream the tutor's final answer token by token (tools still resolve server-side first). The
      provenance guard runs on the assembled text. Keep the non-streaming path as a fallback.

## M11. Proactive tutor explanations

- [ ] "Explain this" on the check-up findings, what-moved, never-sold and the realized breakdown.
      The tutor fetches the authoritative finding by key (numbers from code), so it stays inside
      hard rule #2: it explains an existing fact, never volunteers an opinion.

## M12. Frontend and E2E tests

- [ ] Vitest + Testing Library over `lib/` and the presentational components (runs in CI, no
      backend). Plus a Playwright smoke (sign in, buy, see it on the overview) against a running
      stack, gated on a test Supabase project, to close the "signed-in click-through" step for good.

Explicit non-goals across M7-M12 (same reasoning the earlier ones use): real-time websocket price
ticking (contradicts calm mode), forward return projections (edge toward advice), and Redis or any
shared-cache infrastructure (over-engineering for an invite-only demo).

## Progress log

- 2026-08-13  **M9 (realized vs unrealized) complete.** Splits the account's total gain into where
  it came from, so a beginner can tell money they've banked from a gain that's only on paper. New
  pure `services/analysis/realized.py` replays the ledger with the **same average-cost method the
  sim's engine uses** and books a realized gain on every sell (no new table, no provider call). A
  shared `build_returns` composer in `services/portfolio.py` splits the total into **realized +
  unrealized + dividends**, which reconcile to `total_gain_loss` by construction (asserted in the
  tests). `realized_gain` and `unrealized_gain` ride along on the `/api/portfolio` payload (no
  extra provider cost, so no separate route), a `get_returns_breakdown` tutor tool lets the tutor
  narrate the split within hard rule #1, and a "Where your gain comes from" card lands on Holdings
  with two new glossary terms; the copy explains, never judges. 386 backend tests green (11 new,
  including the reconciliation identity at both the analysis and API levels); ruff + mypy clean;
  web passes eslint + prettier + tsc + a production build.
- 2026-08-13  **M8 (recurring investing) complete.** Automatic investing, the habit the app most
  wants to teach, made real: "put $X into this stock every week/month". New
  `recurring_investments` table (migration 0009, RLS on) and `services/sim/recurring.py`. It
  settles on the **same lazy, no-cron sweep** as the limit orders and dividends, filling through
  the same `buy`/`fill_buy` a manual order uses. Two deliberate rules (see decisions.md):
  **one run per load then realign to the future**, so a long gap fires once instead of stacking a
  pile of identical same-price buys (the price-averaging *lesson* stays in the what-if; this is the
  habit), and **pause, never overdraw**, so a run the account can't afford pauses with a reason the
  user can resume. CRUD routes (create validates the symbol against a live quote; list; PATCH to
  pause/resume; DELETE to cancel), wired into `read_portfolio`'s sweep and cleared by a reset. UI:
  an "Invest automatically" card on the stock page and an "Automatic investing" section on Activity
  with pause/resume/cancel, tied to the existing DCA what-if and glossary term. No new provider and
  no new market-data cost: runs fill at a quote the dashboard fetches anyway. 375 backend tests
  green (26 new); ruff + mypy clean; web passes eslint + prettier + tsc + a production build.
- 2026-08-12  **M7 (dividends) complete.** Companies now pay the account for holding their stock.
  The spike found no free dividend feed (Finnhub's endpoint is premium, Twelve Data's needs the
  paid Grow plan), so dividends come from a **curated, checked-in calendar** for the demo symbols
  behind a swappable `DividendProvider`, a drop-in for a real feed later (see decisions.md). New
  `dividend_payments` table (migration 0008, RLS on), a **cash event of its own, not a
  transaction**, unique on (account, symbol, ex_date). Settlement is **lazy on dashboard load**
  like the order sweep: it pays for shares held *before* each ex-date (reconstructed from the
  ledger), is idempotent, and is cleared by a reset. The money is folded into the performance
  history so the line's endpoint matches the dashboard total, and the **benchmark now accrues the
  index's own dividends** so "vs the S&P" stays an honest total-return comparison instead of
  flattering the dividend collector (a deliberate change to what that chart means; see
  decisions.md). New `dividend_income` on the portfolio payload and a `/api/dividends` ledger; UI
  adds a "companies have paid you $X" line on the overview, a dividends section on Activity, a
  first-time explainer, and two glossary terms. 349 backend tests green (30 new); ruff + mypy
  clean; web passes eslint + prettier + tsc + a production build. Also opened M7-M12 in this doc.
  Signed-in click-through still pending (M12 will automate it).
- 2026-07-28  M6 opened (ship it as a portfolio demo), and the security hardening that started

- 2026-07-28  M6 opened (ship it as a portfolio demo), and the security hardening that started
  it is done. **Enabled RLS on every table and closed the public Supabase Data API**, which was
  serving every row (emails, balances, transactions) to anyone with the browser publishable key;
  confirmed anonymous reads returned real data before and `[]` after. Then **gated signup behind
  a shared invite code**, enforced at the API rather than the form (the form is bypassable via
  Supabase's public signup endpoint): `get_current_user` 403s `invite_required` until a code is
  redeemed at `POST /api/redeem-invite`, and the user row's existence is the "invited" marker, so
  no new table. The signed-in click-through was manually verified. 319 backend tests green (5 new
  for the gate); web builds clean. Remaining M6 is the tutor throttle and OpenAI billing cap,
  auto-seeding new accounts with sample history, error boundaries and a footer disclaimer, the
  `main.py` APIRouter split, README/LICENSE polish, and the Vercel + Render deploy. Implementation
  order: safety and cost, demo experience, repo polish, deploy.
- 2026-07-24  M5 code complete, in thirteen commits. The dashboard was one page doing five
  jobs, which contradicted both stated UX principles, so it **split into three routes**
  (Overview / Holdings / Activity) with the tutor docked in a slide-over reachable from every
  page. Deliberately no fourth "Learn" tab: product-spec warns against one, so the badges sit
  at the bottom of Overview and the glossary hangs off the tutor panel (see decisions.md). Then
  eleven features, most of them surfacing math that already existed. New pure analysis modules
  `checkup.py` (five spread-of-money checks), `movers.py` (which position moved your number)
  and `moves.py` (a big-day note plus the biggest daily moves), plus `never_sold_series` and
  `trim_to` in `history.py` and `spread_over` in `whatif.py`. Two new routes
  (`/api/portfolio/checkup`, `/api/stock/{symbol}/moves`); everything else rode along on
  payloads that already existed.
  **Provider cost was the design constraint throughout** and it came out roughly flat: the
  period selector, the never-sold comparison, the DCA leg, the big-move note and the biggest
  moves all read candles or quotes already cached, and the two things that do spend quota are
  scoped to the page that shows them (the check-up's sector lookup, skipped entirely for a
  single holding; the news archive, one year-wide call per symbol cached six hours rather than
  one call per day). Splitting the pages *lowered* traffic, since the expensive history rebuild
  now fires only on Overview.
  Hard rule #2 did most of the copy work: every composed sentence is written in Python beside
  the rule that computes it, and `checkup`, `movers` and `moves` each carry a test asserting the
  wording never reaches for the imperative or claims a cause. 313 backend tests green (86 new);
  ruff + mypy clean; web passes eslint + prettier + tsc and a production build. Calm mode and
  the mobile header were verified in a browser (the header overflowed a 375px phone by 40px and
  wrapped at 320px before the fix); everything behind the login wall is still checked at the
  HTTP and schema level only, so the **signed-in click-through is the one step left**, same as
  it was for M3 and M4.
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
