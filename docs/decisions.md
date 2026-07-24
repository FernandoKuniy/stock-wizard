# Decision Log

A running record of decisions that diverge from the original plan, newest at the top. One line each: what changed, and why. Claude Code appends here automatically when we lock in a decision that differs from what the docs described. See CLAUDE.md for the routing rules on which doc each kind of decision updates.

Format: `YYYY-MM-DD  what changed  (why)`

## Decisions

- 2026-07-22  The portfolio check-up gets **its own route** (`GET /api/portfolio/checkup`)
  instead of riding along on `/api/portfolio` the way the achievements do. The achievements ride
  along *because* they cost no provider call; the check-up's sector split needs a company profile
  per holding, so the "only fetch what a user is viewing" rule says only the page showing it
  should pay. Profiles cache 24h, so it comes to about one call per symbol per day across
  everyone, and the lookup is skipped outright for a single-holding account (one company is
  trivially all of one industry, which teaches nothing). Its two states are **`ok` and
  `notable`**, not good and bad: this app explains, so "notable" means worth understanding, never
  wrong, and a test asserts the copy never reaches for the imperative. The findings render
  **amber, never red**, since red and green are reserved for money lost and made. A failed
  profile lookup degrades that one check to `unknown` rather than guessing a sector.
- 2026-07-22  The performance chart's period selector **rebases each window** rather than just
  zooming the x-axis. Over a shorter stretch the index leg is rebought at whatever the account
  was worth on that stretch's first day, so both lines still start at the same number and "you're
  beating the market by $310" means over *that* stretch. Slicing while keeping the day-one
  benchmark would have put the two lines at different origins and left a headline that
  contradicted the chart under it. The offered periods are **1M / 6M / 1Y / All only**: a 1D or
  1W view of your own money teaches reading noise as signal, the same reasoning that cut activity
  badges. Slicing happens **server-side** off the already-cached candle window, so switching
  periods costs no provider call; doing it in the browser would have been free too but breaks the
  rule that the frontend only formats and never recomputes a figure.
- 2026-07-22  The dashboard splits into **three routes** (Overview `/`, Holdings `/holdings`,
  Activity `/activity`) instead of the single stacked page it had been through M4. One page
  doing five jobs contradicted both stated UX principles ("one screen answers how am I doing"
  and "show a beginner three buttons, not thirty"), and every extra M5 feature would have made
  it worse. Deliberately **not** a fourth "Learn" destination holding the tutor and the badges:
  product-spec.md warns against a Learn tab nobody visits, and moving the tutor off the one
  screen everyone opens would cost it its whole audience. So the badges stay at the bottom of
  the overview and the tutor stays reachable everywhere. This is a **frontend-only** change: no
  route, schema or analysis change, and each page fetches only what it renders, which *lowers*
  provider traffic (the expensive history rebuild now fires only on the overview, and watchlist
  quotes only for people who open Activity). `/transactions` becomes a permanent redirect to
  `/activity` rather than a fourth page.
- 2026-07-22  Achievements (M4, last extra) reward **understanding and good habits, never
  activity and never outcomes**, which reframes the feature's goal from the product spec's
  "streaks to bring people back" (retention) to **teaching**. A mechanic that pulls a beginner
  into a *trading* app daily nudges them to look at their money daily, which is upstream of
  trading and reacting more, the exact behaviour the benchmark chart exists to warn against;
  and rewarding profit rewards luck and teaches a beginner to read a month of noise as skill.
  So the six badges are all habits whose finance is settled: holding five companies at once,
  holding a position through 1/3/6/12 months, and sitting through a 15%+ dip without selling.
  We deliberately **cut** the mechanics-milestone tier (first buy, first limit order, asked the
  tutor, used the time machine), which keeps every badge to pure lazy detection with no
  event-awarding at other routes. We accept lower engagement as the price of not teaching the
  wrong lesson.
- 2026-07-22  The "streaks" half of the roadmap item ships as **holding duration**, not a
  daily-visit streak. A consecutive-days streak (even a "learning streak") runs on manufactured
  loss aversion and, in this app, the room it pulls you back to is your own portfolio. Holding
  duration is the only streak that correlates with good outcomes, and it comes free from the
  transactions we already store, so it needs no `last_seen_on` column or visits table (keeping
  faith with the 2026-07-14 decision that non-money session state doesn't earn a table).
- 2026-07-22  Achievement detection is **lazy on `GET /api/portfolio`**, the same no-cron shape
  as the limit-order sweep, off the snapshot already in hand so it costs no provider call. The
  result rides along on the portfolio payload rather than adding a route. Awarding is
  **add-only and idempotent** (unique on (account_id, key)); a badge is never revoked and
  **survives a reset**, since it's a learning record, not money. The "held through a dip" badge
  ships in its **cheap form**: it only catches drops below cost basis, because catching a true
  peak-to-trough drawdown would need a second candle fetch per symbol and real pressure on
  Twelve Data's tier. The **AI tutor gets no achievements tool** this milestone: a
  congratulating tutor drifts toward endorsement faster than a static badge does, for no
  teaching gain.
- 2026-07-15  The M4 "time machine" ships as a **what-if calculator** ("what if you'd put $1,000 into this a year ago?"), not the replay mode the vague roadmap line could also have meant, since replaying the market forward from a past date is effectively a second simulation engine for no extra teaching gain. The lookback is capped at two years, the candle window we already fetch and cache, so a what-if on a stock page normally costs no provider call at all; reaching further back would need a second longer fetch per symbol and real pressure on Twelve Data's 8/min tier. The result **always** shows the same money in the index over the same window, because "you'd have made $500" alone reads as a nudge to buy (hard rule #2), and the comparison is dropped rather than drawn if the index can't be priced over that same window. Shares stay exact fractions rather than rounding down to 6dp like a real fill, since a hypothetical that rounds would invent a loss the user never took.
- 2026-07-15  Limit orders fill **lazily**, swept against a fresh quote whenever the user loads their portfolio or their orders, because this app deliberately runs no background job (the same reasoning that made portfolio history a rebuild-on-demand rather than a stored snapshot). A crossed order fills at its **limit price**, not at the quote we happened to see, since the price passed through the limit on its way and filling at a later snapshot would pretend the user timed the move. **Nothing is reserved at placement**: cash moves only at fill, which leaves every existing money figure untouched, so an account can rest more buys than it can afford, oldest-first wins, and one that can no longer be covered is cancelled with a reason rather than part-filled. Orders are good-till-cancelled and all-or-nothing (no expiry status, no partial fills), and a symbol we can't quote is never filled.
- 2026-07-15  `engine.fill_buy`/`fill_sell` were promoted to shared settlement primitives (with `fill_sell` extracted to mirror the existing `fill_buy`), so market orders, the seed backfill, and the limit sweep all bookkeep a fill through the same code and the money math cannot drift between them. `reset` now clears orders before transactions, since a filled order references the trade it became.
- 2026-07-15  Watchlists (M4, first extra) land as account-scoped CRUD over a new `watchlist_items` table with no analysis or sim layer in the path (no money is involved, so a watchlist is just a list of tickers and doesn't need the "numbers" machinery). The list endpoint bundles a live quote per symbol and degrades per-symbol to null like the dashboard's stale holdings; an `include_quotes=false` flag lets the stock page's Watch star check membership without spending quote quota on a ticker the user isn't viewing (the "only fetch what a user is viewing" rule); add validates against a live quote and is idempotent; delete is a 204 no-op. Adding happens via the stock-page star; the dashboard is display-plus-remove.
- 2026-07-15  The AI tutor runs on OpenAI (cheapest current model, `gpt-5.4-nano`, overridable via `TUTOR_MODEL`) behind a swappable `TutorProvider` interface, instead of the Claude/Anthropic default the M3 plan named (the tutor was always designed provider-agnostic per this doc; the model is a config value, not baked in, so the provider is the one thing that changed).
- 2026-07-15  Tutor conversations are ephemeral: the thread lives in the browser and is re-sent each turn, with nothing stored server-side (a chat thread is a UI concern, not money, and doesn't justify a table or migration, matching the localStorage first-time explainers).
- 2026-07-15  Hard rule #1 (numbers come from code) is enforced by architecture (the account-scoped tools are the only source of figures) plus a pure provenance guard that the tests assert over controlled tool output; at runtime the guard logs violations rather than rewriting the model's words, since a probabilistic model can't be unit-tested to "never" and mangling a false positive is worse than a rare stray digit.
- 2026-07-15  Account snapshot and history math were extracted into `services/portfolio.py`, shared by the `/api/portfolio` routes and the tutor's `get_portfolio_summary` / `get_benchmark_comparison` tools, so both surfaces compute identical figures (money numbers must not drift between the dashboard and the tutor).
- 2026-07-15  All six tutor tools shipped in M3, including `get_recent_news` (a new Finnhub company-news fetch, cached ten minutes) and `explain_term` (a small server-side glossary mirroring the frontend), rather than deferring news to the M4 news-feed item.
- 2026-07-14  Portfolio history is reconstructed on demand from the transactions plus real daily closes, NOT stored as daily snapshots (no new table and no scheduled job, exact from an account's first day rather than only from the day we started recording, and it survives a reset).
- 2026-07-14  A holding whose live quote fails is carried in the dashboard totals at its cost basis and flagged in `unpriced_symbols`, instead of being dropped (dropping it shrank the portfolio by the whole position, so a single flaky Finnhub call read as a large loss the user never took).
- 2026-07-14  The history endpoint refuses to draw at all (502) when a held symbol's price history is unavailable, but still draws the user's line when only the *index* is unavailable (a chart that silently omits a position understates someone's money; a wrong chart about your money is worse than no chart, while a missing benchmark only costs the comparison).
- 2026-07-14  `seed --history` backdates a demo account and fills real buys at historical closes via `sim.backfill_buy`, so the benchmark chart has a curve on day one. It is not a back door into the trading API: no route calls it, and live orders still go through `buy()`, which fills at the latest quote and cannot be handed a price.
- 2026-07-14  Candles are always fetched as the long (~2 year) window and sliced, cached 6 hours per symbol, so one call serves both the stock page's chart and the portfolio history (a Twelve Data call costs the same for 90 rows as for 500, and the free tier allows only 8 a minute).
- 2026-07-14  "First-time explainer seen" is kept in localStorage, not the database (it is a UI preference, not money, and does not justify a table or a round trip even now that we have real accounts).
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
