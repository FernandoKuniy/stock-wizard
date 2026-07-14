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

export type Portfolio = {
  cash: number;
  starting_balance: number;
  total_value: number;
  total_cost_basis: number;
  total_gain_loss: number;
  total_gain_loss_percent: number;
  cash_weight: number;
  holdings: Holding[];
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

export type OrderResult = { transaction: Transaction; cash: number };

export type OrderInput = {
  symbol: string;
  side: "buy" | "sell";
  mode: "shares" | "dollars";
  value: number;
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

  return (await res.json()) as T;
}

export const getPortfolio = (token: Token) => request<Portfolio>("/api/portfolio", token);

export const getTransactions = (token: Token) => request<Transaction[]>("/api/transactions", token);

export const resetAccount = (token: Token) =>
  request<Portfolio>("/api/account/reset", token, { method: "POST" });

export const searchSymbols = (query: string, token: Token) =>
  request<SymbolMatch[]>(`/api/search?q=${encodeURIComponent(query)}`, token);

export const getStock = (symbol: string, token: Token) =>
  request<Stock>(`/api/stock/${encodeURIComponent(symbol)}`, token);

export const getCandles = (symbol: string, token: Token) =>
  request<Candles>(`/api/stock/${encodeURIComponent(symbol)}/candles`, token);

export const placeOrder = (order: OrderInput, token: Token) =>
  request<OrderResult>("/api/orders", token, { method: "POST", body: JSON.stringify(order) });
