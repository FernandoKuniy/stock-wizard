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
  // Habit badges, earned and still-locked, detected on this same load from the account's own
  // holdings and trades. Rides along on the portfolio payload rather than its own request.
  achievements: Achievement[];
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

export type PortfolioHistory = {
  starting_balance: number;
  benchmark_symbol: string | null;
  points: HistoryPoint[];
  comparison: BenchmarkComparison | null;
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

export type Stock = { quote: Quote; profile: CompanyProfile | null };

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
    if (res.status === 401) throw new Error("Your session ran out. Sign in again.");

    let detail = `Something went wrong (${res.status}).`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // no JSON body; keep the status-based message
    }
    throw new Error(detail);
  }

  // A 204 (e.g. a DELETE) carries no body, so don't try to parse one.
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const getPortfolio = (token: Token) => request<Portfolio>("/api/portfolio", token);

export const getPortfolioHistory = (token: Token) =>
  request<PortfolioHistory>("/api/portfolio/history", token);

export const getTransactions = (token: Token) => request<Transaction[]>("/api/transactions", token);

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

// The tutor is stateless server-side: the whole thread lives in the browser and is sent back
// each turn. Numbers in the reply are computed by the backend's tools, never by the model.
export type TutorMessage = { role: "user" | "assistant"; content: string };
export type TutorReply = { reply: string };

export const askTutor = (messages: TutorMessage[], token: Token) =>
  request<TutorReply>("/api/tutor", token, {
    method: "POST",
    body: JSON.stringify({ messages }),
  });

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
