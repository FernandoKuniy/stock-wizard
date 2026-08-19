// Typed client for the Stock Wizard backend. Every network call goes through
// here so error handling and the base URL live in one place.
//
// Every call takes the signed-in user's access token, which the backend verifies.
// The token is passed in rather than looked up here, because where it comes from
// depends on where the code runs: lib/supabase/server.ts on the server, and
// lib/supabase/client.ts in the browser.

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Token = string | null;

export type Holding = {
  symbol: string;
  quantity: number;
  avg_cost: number;
  cost_basis: number;
  price: number | null;
  market_value: number | null;
  gain_loss: number | null;
  gain_loss_percent: number | null;
  weight: number | null;
};

// A habit badge. `requirement` is how you earn it (shown even when locked); `lesson` is the
// teaching copy behind it. Both are written by a person, never generated. `earned_at` is null
// until it's earned.
export type Achievement = {
  key: string;
  title: string;
  requirement: string;
  lesson: string;
  earned: boolean;
  earned_at: string | null;
};

export type Portfolio = {
  cash: number;
  starting_balance: number;
  total_value: number;
  total_cost_basis: number;
  total_gain_loss: number;
  total_gain_loss_percent: number;
  cash_weight: number;
  holdings: Holding[];
  // Holdings we couldn't get a live price for. They're counted in the totals at what they
  // cost, so a flaky quote can't read as a loss the user never took.
  unpriced_symbols: string[];
  // One sentence naming the position behind the movement, written server-side, null when
  // nothing has moved. It covers what's held right now, so it deliberately doesn't add up to
  // total_gain_loss, which also holds money banked from things already sold.
  what_moved: string | null;
  // Habit badges, earned and still-locked, detected on this same load from the account's own
  // holdings and trades. Rides along on the portfolio payload rather than its own request.
  achievements: Achievement[];
  // True while this is the demo sample we seeded a new account with, so the UI can offer
  // "hit reset to start your own". A reset clears it.
  is_sample: boolean;
  // Every dividend dollar this account has been paid for holding its stocks. Already part of
  // `cash` and `total_value`; surfaced on its own so the UI can teach that some of the money
  // arrived just for holding. Zero until something has paid out.
  dividend_income: number;
  // The total gain split by where it came from. `realized_gain` is money locked in by selling;
  // `unrealized_gain` is the gain still on paper in what's held. With `dividend_income` these
  // add up to `total_gain_loss` (all computed server-side; the frontend only lays them out).
  realized_gain: number;
  unrealized_gain: number;
};

// One dividend paid into the account for holding a stock through its ex-date. `shares` and
// `per_share` explain the payment ("12.5 shares at $0.51"); `amount` is the cash that landed.
export type Dividend = {
  symbol: string;
  ex_date: string;
  per_share: number;
  shares: number;
  amount: number;
  paid_at: string;
};

// One observation about how your money is spread out. "notable" means worth understanding,
// not wrong: the app explains, it never advises. "unknown" means we couldn't get the data
// for that check (today, only a sector lookup that failed).
export type CheckupStatus = "ok" | "notable" | "unknown";

// `detail` is the sentence with the figure in it and `lesson` is the teaching copy. Both are
// written server-side; the frontend only lays them out.
export type CheckupFinding = {
  key: string;
  title: string;
  status: CheckupStatus;
  detail: string;
  lesson: string;
};

export type HistoryPoint = { date: string; portfolio: number; benchmark: number | null };

export type BenchmarkComparison = {
  portfolio_value: number;
  benchmark_value: number;
  // Positive means you're ahead of the index, in dollars.
  difference: number;
  portfolio_percent: number;
  benchmark_percent: number;
};

// How far back the performance chart looks. Nothing shorter than a month on purpose: a
// day-by-day view of your own money teaches trading on noise.
export type HistoryPeriod = "1m" | "6m" | "1y" | "all";

// `baseline` is where both lines start on this stretch: the starting balance over the
// account's whole life, or what it was worth on the window's first day over a shorter one.
// `starting_balance` is always what the account was funded with.
// What the account would be worth if every buy had simply been held. `difference` is the real
// portfolio minus this one, so positive means the selling has worked out so far. Null unless
// the account has actually sold something, on the whole-life view only.
export type NeverSold = { value: number; difference: number };

export type PortfolioHistory = {
  starting_balance: number;
  period: HistoryPeriod;
  baseline: number;
  benchmark_symbol: string | null;
  points: HistoryPoint[];
  comparison: BenchmarkComparison | null;
  never_sold: NeverSold | null;
};

export type SymbolMatch = { symbol: string; description: string; type: string };

export type Quote = {
  symbol: string;
  price: number;
  change: number;
  percent_change: number;
  high: number;
  low: number;
  open: number;
  previous_close: number;
};

export type CompanyProfile = {
  symbol: string;
  name: string;
  exchange: string;
  industry: string;
  logo: string;
  market_cap: number;
  blurb: string;
};

// `big_move` is set only when today's change is unusual enough to point at. It says the move
// is big, never why: whether the day's headlines explain it is left to the reader.
export type Stock = { quote: Quote; profile: CompanyProfile | null; big_move: string | null };

// One recent article about a company. `date` is an ISO date, or "" if the source omitted it.
// The numbers inside a headline are the source's words, never our computed figures.
export type NewsItem = {
  headline: string;
  summary: string;
  source: string;
  url: string;
  date: string;
};

export type CandlePoint = { date: string; close: number };
export type Candles = { symbol: string; points: CandlePoint[] };

// One notable trading day. `news` is empty far more often than not: a day with no headline is
// the normal case, never an error.
export type DayMove = {
  date: string;
  percent_change: number;
  close: number;
  news: NewsItem[];
};

// The handful of days that did most of a stock's moving. `trading_days` is how many days
// moved at all, which is the number that makes the point. Either list can be empty.
export type BiggestMoves = {
  symbol: string;
  trading_days: number;
  up: DayMove[];
  down: DayMove[];
};

export type Transaction = {
  id: number;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  total: number;
  timestamp: string;
};

// A limit order waiting for its price. `cancel_reason` is set only when we cancelled it on
// the user's behalf, because the cash or the shares were gone by the time the price arrived.
export type Order = {
  id: number;
  symbol: string;
  side: string;
  quantity: number;
  limit_price: number;
  status: "open" | "filled" | "cancelled";
  created_at: string;
  resolved_at: string | null;
  cancel_reason: string | null;
};

// A market order fills immediately and comes back as a transaction; a limit order rests and
// comes back as an order. Exactly one of the two is set.
export type OrderResult = {
  transaction: Transaction | null;
  order: Order | null;
  cash: number;
};

export type OrderInput = {
  symbol: string;
  side: "buy" | "sell";
  mode: "shares" | "dollars";
  value: number;
  type?: "market" | "limit";
  limit_price?: number;
};

// An error from the backend that keeps the HTTP status and, when the backend sent one, a
// machine-readable `code`. The code is how the frontend tells apart cases that look alike as
// prose but need different handling, like "you need an invite code" versus a plain failure.
export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

// True when the backend refused because the signed-in user hasn't redeemed an invite code
// yet. The gate lives on the server (see api/auth.py), so this is how a page learns to send
// them to the redeem screen instead of showing an error.
export function isInviteRequired(e: unknown): boolean {
  return e instanceof ApiError && e.code === "invite_required";
}

// True when a demo account has spent its tutor allowance. The cap is enforced server-side
// (see api/routers/tutor.py), so this is how the panel knows to show the "ask for a code"
// banner even if the client's own count is stale.
export function isDemoLimitReached(e: unknown): boolean {
  return e instanceof ApiError && e.code === "demo_limit_reached";
}

async function request<T>(path: string, token: Token, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    // Always hit the backend: balances and prices must be live, never cached.
    cache: "no-store",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });

  if (!res.ok) {
    if (res.status === 401) throw new ApiError("Your session ran out. Sign in again.", 401);

    let message = `Something went wrong (${res.status}).`;
    let code: string | undefined;
    try {
      const body = await res.json();
      const detail = body?.detail;
      if (typeof detail === "string") {
        message = detail;
      } else if (detail && typeof detail === "object") {
        // A structured error: a machine-readable `code` plus a human `message` (the invite
        // gate is the one that sends this shape today).
        if (typeof detail.message === "string") message = detail.message;
        if (typeof detail.code === "string") code = detail.code;
      }
    } catch {
      // no JSON body; keep the status-based message
    }
    throw new ApiError(message, res.status, code);
  }

  // A 204 (e.g. a DELETE) carries no body, so don't try to parse one.
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// Who the signed-in user is, and whether they've redeemed an invite code. `provisioned` is
// false for someone who is signed in but hasn't been let past the gate yet.
//
// `is_demo` marks an account opened with the published demo code: everything works except
// that the tutor has a lifetime allowance, and `tutor_messages_left` counts it down. A full
// account has no allowance to count, so it reports null.
export type Me = {
  email: string;
  provisioned: boolean;
  is_demo: boolean;
  tutor_messages_left: number | null;
};

// Answers even for a not-yet-invited user (it doesn't go through the account gate), so the
// layout can tell "signed in" from "actually let in" and pick the right header.
export const getMe = (token: Token) => request<Me>("/api/me", token);

// Trade a valid invite code for a funded account. Redeeming when already provisioned is a
// harmless no-op, so a retry or a stale tab can't lock anyone out.
// The response reports the tier the account ended up on, which is how the tutor's "already
// have a code?" form tells a real upgrade from a no-op: redeeming is deliberately forgiving,
// so a wrong code comes back ok, just still on the demo tier.
export const redeemInvite = (code: string, token: Token) =>
  request<{ status: string; is_demo: boolean }>("/api/redeem-invite", token, {
    method: "POST",
    body: JSON.stringify({ code }),
  });

export const getPortfolio = (token: Token) => request<Portfolio>("/api/portfolio", token);

// Its own call rather than riding on the portfolio payload: this one looks up a company
// profile per holding for the sector split, so only the page that shows it should pay for it.
export const getCheckup = (token: Token) =>
  request<CheckupFinding[]>("/api/portfolio/checkup", token);

// Switching periods costs no market-data call: the backend builds the series over the whole
// account either way, off candles it has already cached, and slices it.
export const getPortfolioHistory = (token: Token, period: HistoryPeriod = "all") =>
  request<PortfolioHistory>(`/api/portfolio/history?period=${period}`, token);

export const getTransactions = (token: Token) => request<Transaction[]>("/api/transactions", token);

// A pure read: dividends are settled when the dashboard loads (getPortfolio), so this just
// lists what's already been paid and spends no market-data call.
export const getDividends = (token: Token) => request<Dividend[]>("/api/dividends", token);

export const resetAccount = (token: Token) =>
  request<Portfolio>("/api/account/reset", token, { method: "POST" });

export const searchSymbols = (query: string, token: Token) =>
  request<SymbolMatch[]>(`/api/search?q=${encodeURIComponent(query)}`, token);

export const getStock = (symbol: string, token: Token) =>
  request<Stock>(`/api/stock/${encodeURIComponent(symbol)}`, token);

export const getCandles = (symbol: string, token: Token) =>
  request<Candles>(`/api/stock/${encodeURIComponent(symbol)}/candles`, token);

export const getNews = (symbol: string, token: Token) =>
  request<NewsItem[]>(`/api/stock/${encodeURIComponent(symbol)}/news`, token);

// The moves come off the cached candle window the price chart already used, so they're free.
// The headlines are one archive fetch per symbol, cached for hours on the backend.
export const getBiggestMoves = (symbol: string, token: Token) =>
  request<BiggestMoves>(`/api/stock/${encodeURIComponent(symbol)}/moves`, token);

// One side of a what-if: what the money bought, and what it's worth at the latest close.
export type WhatIfLeg = {
  symbol: string;
  shares: number;
  bought_on: string;
  buy_price: number;
  value_now: number;
  gain_loss: number;
  gain_loss_percent: number;
};

// The same total money drip-fed monthly instead of all at once. `each` is one instalment;
// they add up to exactly the amount, so this and the lump sum really are the same money.
export type SpreadLeg = {
  symbol: string;
  instalments: number;
  each: number;
  shares: number;
  first_on: string;
  last_on: string;
  value_now: number;
  gain_loss: number;
  gain_loss_percent: number;
};

export type WhatIfPeriod = "1m" | "6m" | "1y" | "2y";

// `benchmark` and `difference` are null when the index couldn't be priced over the same
// window. `difference` is positive when the stock beat the index.
export type WhatIf = {
  amount: number;
  period: string;
  latest_on: string;
  stock: WhatIfLeg;
  benchmark: WhatIfLeg | null;
  difference: number | null;
  // Null over a one-month window, which is too short to split into instalments.
  spread: SpreadLeg | null;
};

// Served from the same cached candle window the price chart already fetched, so this
// normally costs no provider call.
export const getWhatIf = (
  symbol: string,
  token: Token,
  { amount = 1000, period = "1y" }: { amount?: number; period?: WhatIfPeriod } = {},
) =>
  request<WhatIf>(
    `/api/stock/${encodeURIComponent(symbol)}/what-if?amount=${amount}&period=${period}`,
    token,
  );

export const placeOrder = (order: OrderInput, token: Token) =>
  request<OrderResult>("/api/orders", token, { method: "POST", body: JSON.stringify(order) });

// Loading this settles any resting order whose price has arrived, since the app runs no
// background job. Same for getPortfolio.
export const getOrders = (token: Token) => request<Order[]>("/api/orders", token);

export const cancelOrder = (id: number, token: Token) =>
  request<Order>(`/api/orders/${id}`, token, { method: "DELETE" });

// An automatic investment: a fixed dollar amount into a symbol every week or month, filled by
// the same lazy sweep as a limit order when the dashboard loads. `paused_reason` is set only
// when we paused it because the cash was gone; `last_run_on` is null until the first buy fires.
export type RecurringCadence = "weekly" | "monthly";

export type Recurring = {
  id: number;
  symbol: string;
  amount: number;
  cadence: RecurringCadence;
  next_run_on: string;
  last_run_on: string | null;
  active: boolean;
  paused_reason: string | null;
  created_at: string;
};

export const getRecurring = (token: Token) => request<Recurring[]>("/api/recurring", token);

export const createRecurring = (
  input: { symbol: string; amount: number; cadence: RecurringCadence },
  token: Token,
) => request<Recurring>("/api/recurring", token, { method: "POST", body: JSON.stringify(input) });

// Pause (active=false) or resume (active=true) a schedule. Resuming makes the next buy due on
// the next dashboard load.
export const updateRecurring = (id: number, active: boolean, token: Token) =>
  request<Recurring>(`/api/recurring/${id}`, token, {
    method: "PATCH",
    body: JSON.stringify({ active }),
  });

export const deleteRecurring = (id: number, token: Token) =>
  request<void>(`/api/recurring/${id}`, token, { method: "DELETE" });

// The tutor is stateless server-side: the whole thread lives in the browser and is sent back
// each turn. Numbers in the reply are computed by the backend's tools, never by the model.
export type TutorMessage = { role: "user" | "assistant"; content: string };
export type TutorReply = { reply: string };

export const askTutor = (messages: TutorMessage[], token: Token) =>
  request<TutorReply>("/api/tutor", token, {
    method: "POST",
    body: JSON.stringify({ messages }),
  });

// Stream the tutor's reply token by token, calling `onDelta` for each chunk as it arrives.
// Same account-scoped tools and "numbers from code" guard as askTutor; only the delivery differs.
// The server sends SSE events, each a JSON object: {delta}, {error}, or {done}. Throws an
// ApiError if the request fails to start or an error event arrives mid-stream.
export async function streamTutor(
  messages: TutorMessage[],
  token: Token,
  onDelta: (text: string) => void,
): Promise<void> {
  const res = await fetch(`${API_URL}/api/tutor/stream`, {
    method: "POST",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ messages }),
  });

  if (!res.ok || !res.body) {
    if (res.status === 401) throw new ApiError("Your session ran out. Sign in again.", 401);
    let message = `Something went wrong (${res.status}).`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") message = body.detail;
    } catch {
      // no JSON body; keep the status-based message
    }
    throw new ApiError(message, res.status);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE events are separated by a blank line; each carries one `data:` JSON payload.
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, sep).trim();
      buffer = buffer.slice(sep + 2);
      if (!raw.startsWith("data:")) continue;
      const event = JSON.parse(raw.slice(5).trim());
      if (typeof event.error === "string") throw new ApiError(event.error, 502);
      if (typeof event.delta === "string") onDelta(event.delta);
      // {done: true} just ends the stream; the loop exits when the body closes.
    }
  }
}

// A stock the user is tracking without owning. Price fields are null when the live quote
// is unavailable, the same way a holding degrades, so one flaky quote never hides the list.
export type WatchlistItem = {
  symbol: string;
  price: number | null;
  percent_change: number | null;
};

// Pass includeQuotes=false when you only need to know what's watched (the stock page's
// star), so the backend doesn't spend quote quota on tickers the user isn't looking at.
export const getWatchlist = (token: Token, includeQuotes = true) =>
  request<WatchlistItem[]>(`/api/watchlist?include_quotes=${includeQuotes}`, token);

export const addToWatchlist = (symbol: string, token: Token) =>
  request<WatchlistItem>("/api/watchlist", token, {
    method: "POST",
    body: JSON.stringify({ symbol }),
  });

export const removeFromWatchlist = (symbol: string, token: Token) =>
  request<void>(`/api/watchlist/${encodeURIComponent(symbol)}`, token, { method: "DELETE" });
