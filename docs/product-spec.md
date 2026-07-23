# Product Spec

## One-liner

A risk-free way to learn investing by using fake money in real markets, with an AI tutor
that explains your own portfolio to you.

## Who it's for

People who have never invested and find the stock market intimidating. Assume they do not
know what P/E, market cap, dividend, or ETF mean. The product should make them feel capable,
not stupid. Every piece of jargon is one tap away from a plain definition.

## Core loop (MVP)

This is the smallest thing that feels real and useful. Build this first, no AI yet.

1. Account with a starting fake balance. Default $100,000. Round numbers feel less
   intimidating than odd ones.
2. Search a ticker, land on a stock page with: current price, a simple price chart, and a
   one-line plain-English "what is this company" blurb.
3. Buy and sell. Market orders only to start, filled at the latest quote. Sized by dollar
   amount or share quantity, with fractional shares (the beginner-friendly default).
4. Portfolio dashboard: holdings, total value, cash left, total gain/loss, an allocation
   donut, and the performance chart against the S&P 500. This is the screen that answers
   "how am I doing?" and it is the default landing view.
5. Transaction history.
6. Reset button. Huge for beginners. Let them wipe the slate and start over with no fear.

## Later features (after the core loop feels good)

- Limit orders, introduced as a teaching moment. The first time a user sees them, explain
  market vs limit inline.
- Watchlists.
- Per-stock news feed (Finnhub provides this).
- Historical "time machine" mode: start in a past year, fast-forward, see how you would have
  done. Teaches compounding and volatility in a way that actually lands.
- Achievements that reward good habits, not activity or outcomes. The original framing was
  "streaks to bring people back", but a mechanic that pulls a beginner into a trading app
  daily nudges them to trade and react more, the exact behaviour the benchmark chart warns
  against. So these reward understanding and patience instead: holding several companies,
  holding a position for months, and sitting through a dip without panic-selling. Each badge
  is named for the fact it marks (not the praise), and opens a short explainer, which is the
  real point. No activity or profit badges, and no daily-visit streak; the only "streak" is
  how long you leave a position alone, which is the one that lines up with good outcomes. See
  decisions.md (2026-07-22) for why the goal shifted from retention to teaching.

## Education approach: teach in the flow

Do NOT build a separate "Learn" tab that nobody visits. Weave teaching into the product:

- Hover or tap tooltips on every jargon term (P/E, market cap, dividend yield, volume).
- A one-line "why did this move?" on big price changes, pulled from news.
- Short contextual explainers that appear the first time a user hits a new concept, then
  get out of the way.
- Plain-language money framing everywhere. "You made $240" beats "up 2.4%."

## UX principles

- One screen answers "how am I doing?" the second they log in. No hunting.
- Progressive disclosure. Show a beginner three buttons, not thirty. Advanced order types
  and chart tools unlock as they go.
- Green and red always come with an explanation attached, never a naked number.
- Zero jargon by default, jargon on tap.
- The reset button and the "vs the index" comparison are the two features that most reduce
  beginner anxiety. Treat both as core, not nice-to-have.

## Explicit non-goals

- Not a real brokerage. No real money, ever.
- Not a day-trading terminal. We are optimizing for a nervous beginner, not a power user.
- The AI does not give buy/sell recommendations. It teaches. (See CLAUDE.md hard rule 2.)
