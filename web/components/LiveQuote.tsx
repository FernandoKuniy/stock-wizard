"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Quote = {
  symbol: string;
  price: number;
  change: number;
  percent_change: number;
};

export function LiveQuote({ symbol }: { symbol: string }) {
  const [quote, setQuote] = useState<Quote | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetch(`${API_URL}/api/quote/${symbol}`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`request failed (${res.status})`);
        return (await res.json()) as Quote;
      })
      .then((data) => {
        if (active) setQuote(data);
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : "something went wrong");
      });
    return () => {
      active = false;
    };
  }, [symbol]);

  if (error) {
    return (
      <p className="text-sm text-red-500">
        Couldn&apos;t load {symbol}: {error}
      </p>
    );
  }

  if (!quote) {
    return <p className="text-sm text-zinc-500">Loading {symbol}…</p>;
  }

  const up = quote.change >= 0;
  const sign = up ? "+" : "";
  return (
    <div className="rounded-xl border border-zinc-200 px-6 py-4 dark:border-zinc-800">
      <div className="text-sm text-zinc-500">{quote.symbol}</div>
      <div className="text-3xl font-semibold tabular-nums">${quote.price.toFixed(2)}</div>
      <div className={`text-sm tabular-nums ${up ? "text-green-600" : "text-red-600"}`}>
        {sign}
        {quote.change.toFixed(2)} ({sign}
        {quote.percent_change.toFixed(2)}%) today
      </div>
    </div>
  );
}
