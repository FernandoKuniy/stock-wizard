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

## Screens

Three destinations, one job each. The dashboard used to stack everything on one page, which
meant the first screen answered five questions at once and contradicted both UX principles
below. Splitting it is what lets the overview answer only "how am I doing?".

- **Overview** (`/`): total value, gain/loss, the performance chart against the S&P 500, a
  three-line strip of what you own, the habit badges, and the reset button. The landing
  screen, and the only one a nervous beginner has to read.
- **Holdings** (`/holdings`): the portfolio check-up, the allocation donut, and the full
  holdings table.
- **Activity** (`/activity`): waiting limit orders, the watchlist, and the full transaction
  history. (`/transactions` redirects here.)

The AI tutor is not one of the three. It sits in the header on every page and opens in a
slide-over panel, including on a stock page, which is where "what does market cap mean?"
actually gets asked. `/glossary` hangs off the bottom of that panel: it's the same "I don't
know what that means" moment, so it doesn't need a nav slot of its own.

There is deliberately no fourth "Learn" destination, for the reason in the next section. The
glossary is not one: it holds no lessons and no course, only the words the app already uses,
in one place, so someone can look one up without hunting for the screen that mentions it.

## Education approach: teach in the flow

Do NOT build a separate "Learn" tab that nobody visits. Weave teaching into the product:

- Hover or tap tooltips on every jargon term (P/E, market cap, dividend yield, volume).
- A one-line "why did this move?" on big price changes, pulled from news.
- Short contextual explainers that appear the first time a user hits a new concept, then
  get out of the way.
- Plain-language money framing everywhere. "You made $240" beats "up 2.4%."

## UX principles

- One screen answers "how am I doing?" the second they log in. No hunting. That screen is the
  overview, and it does not do anything else.
- Progressive disclosure. Show a beginner three buttons, not thirty. Advanced order types
  and chart tools unlock as they go. The nav is three destinations for the same reason, and
  a section with nothing in it says so in a line rather than filling the page.
- Green and red always come with an explanation attached, never a naked number.
- Zero jargon by default, jargon on tap.
- The reset button and the "vs the index" comparison are the two features that most reduce
  beginner anxiety. Treat both as core, not nice-to-have.
- Calm mode ("Hide amounts", in the header) blurs the money figures on the two screens that
  judge you, Overview and Holdings, and leaves the direction words readable. The one thing a
  nervous beginner reliably does wrong is react to a red number, so being able to check in
  without a figure to chew on is a real feature, not a gimmick. Hovering a blurred figure
  reveals it, so looking on purpose stays one gesture away.

## Explicit non-goals

- Not a real brokerage. No real money, ever.
- Not a day-trading terminal. We are optimizing for a nervous beginner, not a power user.
- The AI does not give buy/sell recommendations. It teaches. (See CLAUDE.md hard rule 2.)
