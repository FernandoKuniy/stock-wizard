# Stock Wizard

A paper-trading web app that teaches first-time investors. Users invest fake money in
real markets at real prices, and an AI tutor explains what's happening in plain English.
Simulation only, real market data, education first.

## What this project is

- Users get a fake cash balance and buy/sell real stocks and ETFs at real prices.
- The target user has never invested. Assume zero jargon knowledge.
- The whole point is teaching in the flow: contextual explanations everywhere, plus an
  AI tutor that reads the user's own portfolio and explains it back to them.
- This is educational simulation, NOT financial advice. See the two hard rules below.

## Two hard rules (do not break these)

1. **IMPORTANT: Numbers come from code, words come from the LLM.** Every financial figure
   (returns, profit/loss, position weights, concentration, volatility, benchmark
   comparison) is computed by deterministic Python in the analysis layer. The LLM never
   calculates or invents a number. It only explains figures the code already produced.
   This is what keeps the app accurate and trustworthy.
2. **IMPORTANT: Education, never advice.** The AI tutor explains, teaches, and describes
   tradeoffs. It never tells a user to buy or sell a specific security. Everything is
   framed as learning. Keep a visible disclaimer that this is a simulation for education.

## Tech stack

- Frontend: Next.js (App Router) + TypeScript + Tailwind. Charts with Recharts.
- Backend: Python + FastAPI. Postgres for users, cash balances, holdings, transactions.
- Auth: Supabase Auth (email + password). The API verifies access tokens locally against the
  project's public JWKS. IMPORTANT: Supabase RLS does NOT protect our tables (we connect
  straight to Postgres, not through PostgREST), so every route must scope its queries to
  `get_current_account`. That scoping is the only thing keeping one user's money out of
  another's. See architecture.md.
- Market data: Finnhub for quotes, company profiles, symbol search, and news (60 calls/min
  free, real-time US quotes). Twelve Data for historical price candles, since Finnhub's free
  tier dropped them. Any provider works behind the market client, and all providers stay
  inside `services/market/`.
- Simulation: we run our own. Market orders fill at the latest quote. No third-party
  execution engine, which keeps it simple and multi-user native. (See architecture.md for
  why we do not use Alpaca's paper engine per user.)
- AI tutor: an LLM with read-only tool-calling over the user's portfolio. The tools return
  code-computed figures; the LLM narrates.
- Package managers: uv for Python, pnpm for the frontend. Always use these, never pip or npm.

## Commands

Fill these in as the project takes shape. Keep them exact so Claude Code runs them verbatim.

- Frontend dev: `cd web && pnpm dev`
- Backend dev: `cd api && uv run uvicorn main:app --reload`
- Top up an account: `cd api && uv run python -m seed --email you@example.com` (accounts open
  themselves, funded, on first sign-in, so this is only for topping one up by hand)
- Backend tests: `cd api && uv run pytest`
- Lint/format (api): `uv run ruff check .` and `uv run ruff format .`
- Lint/format (web): `pnpm lint` and `pnpm exec prettier --write .`

## Project layout

- `web/` Next.js frontend
- `api/` FastAPI backend
  - `api/services/market/` Finnhub client. ALL external data calls and ALL caching live here.
  - `api/services/sim/` the paper-trading engine (cash, order fills, holdings, transactions).
  - `api/services/analysis/` deterministic portfolio math. This is the "numbers" layer.
  - `api/services/tutor/` the AI tutor. This is the "words" layer. It calls analysis as tools.
- `docs/` the specs below

## Working rules

- Build one milestone at a time from `docs/roadmap.md`. Do not scaffold the whole app at
  once. Mark a milestone done only after it works end to end, then update the roadmap.
- Cache all market data aggressively. Only fetch prices for tickers a user is actively
  viewing. Free API tiers die from sloppy polling, not from real traffic.
- Nothing outside `services/market/` calls Finnhub directly. Route every external call
  through that client so caching and provider swaps stay in one place.
- Never put real secrets in code. Use env vars. Keys live in `.env` (gitignored).
- Prefer boring, readable code over clever code. This is a teaching product, so the
  codebase should be teachable too.

## Engineering standards

Hold the codebase to a standard a senior engineer would respect on first read. That means
disciplined and right-sized, not maximal. Do NOT over-engineer: no premature abstractions,
no extra services or infra the current milestone does not need. The most impressive thing
here is clean, well-tested, consistent code at the right scale.

- Types everywhere. Backend is fully type-hinted and passes `mypy`. Frontend is TypeScript
  in strict mode. No `any` without a comment explaining why.
- Lint and format on every change. Backend: `ruff` for both linting and formatting.
  Frontend: `eslint` and `prettier`. Code passes all of them before a milestone is marked done.
- Test the layers that hold real logic. The sim and analysis layers get thorough unit tests,
  since they are pure functions and their correctness is literally people's balances. Mock
  the market client so tests never hit Finnhub or burn quota.
- Every external call handles failure. Finnhub can be slow, rate-limited, or down. No
  unhandled network error reaches the user. Degrade gracefully with a clear message.
- Separation of concerns is enforced by the layout above. Market, sim, analysis, and tutor
  stay in their own layers and talk through clear function boundaries. No cross-layer
  reach-arounds.
- Secrets only in env vars, never in code or git. Ship a `.env.example` with names, no values.
- Commits are small and focused, one logical change each, and follow Conventional Commits.
- Keep a real README: what it is, how to run it, a one-paragraph architecture summary, and a
  pointer to `docs/`. It is the first thing anyone sees, so make it good.

## Keep the docs in sync (do this automatically)

When we make a decision that changes or extends what these docs describe, update the docs in
the same change. The docs must always reflect the current design, never an abandoned one.

- Product, feature, or UX decisions: update `docs/product-spec.md`.
- Data model, integrations, AI design, or other technical decisions: update `docs/architecture.md`.
- Scope, milestone, or ordering changes: update `docs/roadmap.md`.
- Changes to the stack, the two hard rules, the layout, or the commands: update this file.
- For any material decision that diverges from the original plan, also append a dated
  one-line entry to `docs/decisions.md` with what changed and why.

Only record material decisions that contradict or extend what's written. Do not log routine
implementation detail. For a large divergence from the original vision, confirm with me
before locking it into the docs.

## Deeper docs (read when relevant, not every session)

- `docs/product-spec.md` features (MVP vs later), the education approach, UX principles
- `docs/architecture.md` data model, API integration, AI tutor design, caching
- `docs/decisions.md` running log of decisions that diverge from the original plan
- `docs/roadmap.md` the build plan and running progress log

## Voice for all user-facing copy

- Casual and human. Write like a person, not a bank.
- No em dashes. No corporate speak. No filler.
- Short and concrete. Explain money in plain terms ("you'd have $120 more than you started"),
  not raw percentages alone.

## Commit messages

Use Conventional Commits: `type(optional scope): short description`, present tense,
lowercase description, no trailing period.

- Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`, `build`, `perf`, `style`.
- Keep the subject under ~72 characters. Add a body only when the change needs context.
- One logical change per commit.
- Breaking changes: add `!` after the type (e.g. `feat!:`) or a `BREAKING CHANGE:` footer.
- Keep the plain, no-fluff tone. No em dashes.

Examples:
- `feat(portfolio): add benchmark line vs the S&P 500`
- `fix(market): handle Finnhub rate-limit errors gracefully`
- `chore: add project docs, CI, and tooling config`
