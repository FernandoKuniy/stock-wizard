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

- `users`: id, email, created_at.
- `accounts`: id, user_id, cash_balance, starting_balance, created_at. (One per user for
  now. The starting_balance lets us compute total return and power the reset.)
- `holdings`: id, account_id, symbol, quantity, avg_cost. (avg_cost drives per-position P/L.)
- `transactions`: id, account_id, symbol, side (buy/sell), quantity, price, timestamp.
- `watchlist_items` (later): id, account_id, symbol.

Reset = set cash_balance back to starting_balance, delete holdings and transactions for
that account.

## Market data layer (`services/market/`)

All Finnhub calls and all caching live here. Nothing else touches Finnhub.

- Quotes: current price for a symbol. Cache with a short TTL (a few seconds to a minute is
  fine for an educational app, and the free tier is delayed anyway).
- Candles: historical bars for charts. Cache longer (these do not change intraday for past
  days).
- Company profile: name, sector, logo, description. Cache for a long time (rarely changes).
- News: recent articles per symbol. Cache for minutes.

Caching rules that keep us under the free tier:

- Only fetch a quote when a user is actually viewing that symbol or holds it and is on the
  portfolio screen. Never poll the whole universe.
- Batch and dedupe. If ten things need AAPL's price in the same tick, make one call.
- Cache aggressively per the TTLs above. Free tiers die from sloppy loops, not real load.

## Simulation layer (`services/sim/`)

The paper-trading engine. Pure, testable functions:

- `buy(account, symbol, quantity)`: get latest quote, verify cash, debit cash, upsert
  holding (recompute avg_cost), write a transaction.
- `sell(account, symbol, quantity)`: verify shares held, credit cash, reduce/remove holding,
  write a transaction.
- `reset(account)`: restore starting balance, clear holdings and transactions.

Keep this layer free of HTTP and framework code so it is easy to unit test.

## Analysis layer (`services/analysis/`) — the "numbers"

This is the source of truth for every figure the UI or the AI shows. All deterministic
Python. No LLM anywhere near it.

Operators to build:

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

- `FINNHUB_API_KEY`, `DATABASE_URL`, and the LLM API key live in `.env`, gitignored.
- Provide a `.env.example` with the variable names and no values.

## Testing approach

- Unit test the sim and analysis layers hard. They are pure functions and they are where
  correctness matters most (real balances, real math).
- Mock the market client in tests so tests do not hit Finnhub or burn quota.
