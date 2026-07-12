// Typed client for the Stock Wizard backend. Every network call goes through
// here so error handling and the base URL live in one place.

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    // Always hit the backend: balances and prices must be live, never cached.
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
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

export const getPortfolio = () => request<Portfolio>("/api/portfolio");

export const getTransactions = () => request<Transaction[]>("/api/transactions");

export const resetAccount = () => request<Portfolio>("/api/account/reset", { method: "POST" });

export const searchSymbols = (query: string) =>
  request<SymbolMatch[]>(`/api/search?q=${encodeURIComponent(query)}`);

export const getStock = (symbol: string) =>
  request<Stock>(`/api/stock/${encodeURIComponent(symbol)}`);

export const getCandles = (symbol: string) =>
  request<Candles>(`/api/stock/${encodeURIComponent(symbol)}/candles`);

export const placeOrder = (order: OrderInput) =>
  request<OrderResult>("/api/orders", { method: "POST", body: JSON.stringify(order) });
