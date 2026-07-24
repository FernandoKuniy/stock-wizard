"use client";

import { useEffect, useRef, useState } from "react";

import { getWhatIf, type WhatIf, type WhatIfPeriod } from "@/lib/api";
import { formatMoney, formatPercent, formatShortDate } from "@/lib/format";
import { getAccessToken } from "@/lib/supabase/client";
import { Term } from "./Term";

const PERIODS: { value: WhatIfPeriod; label: string; phrase: string }[] = [
  { value: "1m", label: "1 month", phrase: "a month ago" },
  { value: "6m", label: "6 months", phrase: "six months ago" },
  { value: "1y", label: "1 year", phrase: "a year ago" },
  { value: "2y", label: "2 years", phrase: "two years ago" },
];

/**
 * The time machine: what a lump sum into this stock back then would be worth now.
 *
 * Always shown next to the same money in the S&P 500, on purpose. "You'd have made $500" on
 * its own reads as a reason to buy; next to the index it becomes the lesson the whole app is
 * built around, and it just as often shows the stock trailing the market. Every figure comes
 * from the backend, computed in code. Nothing here does money math.
 */
export function TimeMachine({ symbol, initial }: { symbol: string; initial: WhatIf | null }) {
  const [amountText, setAmountText] = useState("1000");
  const [period, setPeriod] = useState<WhatIfPeriod>("1y");
  const [result, setResult] = useState<WhatIf | null>(initial);
  const [error, setError] = useState<string | null>(initial ? null : "Couldn't work that out.");
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  function load(amount: number, next: WhatIfPeriod) {
    setBusy(true);
    setError(null);
    getAccessToken()
      .then((token) => getWhatIf(symbol, token, { amount, period: next }))
      .then((data) => setResult(data))
      .catch((e: unknown) => {
        setResult(null);
        setError(e instanceof Error ? e.message : "Couldn't work that out.");
      })
      .finally(() => setBusy(false));
  }

  function onAmountChange(next: string) {
    setAmountText(next);
    const amount = Number(next);
    if (timer.current) clearTimeout(timer.current);
    if (!next.trim() || !Number.isFinite(amount) || amount <= 0) return;
    // Wait for the typing to settle rather than firing a request per keystroke.
    timer.current = setTimeout(() => load(amount, period), 400);
  }

  function onPeriodChange(next: WhatIfPeriod) {
    setPeriod(next);
    const amount = Number(amountText);
    if (Number.isFinite(amount) && amount > 0) load(amount, next);
  }

  const phrase = PERIODS.find((p) => p.value === period)?.phrase ?? "back then";

  return (
    <div className="rounded-xl border border-zinc-200 p-5 dark:border-zinc-800">
      <h2 className="text-sm font-medium">What if you&apos;d bought earlier?</h2>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1.5 rounded-lg border border-zinc-200 px-3 py-1.5 text-sm dark:border-zinc-800">
          <span className="text-zinc-500">$</span>
          <input
            type="text"
            inputMode="decimal"
            value={amountText}
            onChange={(e) => onAmountChange(e.target.value)}
            aria-label="Amount to invest"
            className="w-20 bg-transparent tabular-nums outline-none"
          />
        </label>
        <div className="flex flex-wrap gap-1.5 text-xs">
          {PERIODS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => onPeriodChange(option.value)}
              className={`rounded-full px-3 py-1 ${
                period === option.value
                  ? "bg-zinc-900 text-white dark:bg-white dark:text-zinc-900"
                  : "text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-900"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div className={`mt-4 ${busy ? "opacity-50" : ""}`}>
        {error && <p className="text-sm text-zinc-500">{error}</p>}

        {result && !error && (
          <>
            <p className="text-sm">
              If you&apos;d put {formatMoney(result.amount)} into {symbol} {phrase}, you&apos;d have{" "}
              <span className="font-semibold">{formatMoney(result.stock.value_now)}</span> today.
            </p>
            <p
              className={`mt-1 text-sm tabular-nums ${
                result.stock.gain_loss >= 0 ? "text-green-600" : "text-red-600"
              }`}
            >
              {result.stock.gain_loss >= 0 ? "Up" : "Down"}{" "}
              {formatMoney(Math.abs(result.stock.gain_loss))} (
              {formatPercent(result.stock.gain_loss_percent)}).
            </p>

            {result.benchmark && result.difference !== null && (
              <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-300">
                The same money in the S&P 500 would be {formatMoney(result.benchmark.value_now)}, so{" "}
                {symbol} came out{" "}
                <span className="font-medium">
                  {formatMoney(Math.abs(result.difference))}{" "}
                  {result.difference >= 0 ? "ahead of" : "behind"}
                </span>{" "}
                the market.
              </p>
            )}

            {result.spread && (
              <div className="mt-3 rounded-lg border border-zinc-100 bg-zinc-50/60 px-3 py-2.5 dark:border-zinc-800 dark:bg-zinc-900/40">
                <p className="text-sm text-zinc-700 dark:text-zinc-300">
                  Putting in {formatMoney(result.spread.each)} a month instead, over the same{" "}
                  {result.spread.instalments} months, you&apos;d have{" "}
                  <span className="font-medium">{formatMoney(result.spread.value_now)}</span>, so{" "}
                  {formatMoney(Math.abs(result.spread.value_now - result.stock.value_now))}{" "}
                  {result.spread.value_now >= result.stock.value_now ? "more" : "less"} than buying
                  it all at once.
                </p>
                <p className="mt-1.5 text-xs text-zinc-400">
                  That&apos;s the same total money, just spread out. It&apos;s called{" "}
                  <Term name="dollar-cost averaging">dollar-cost averaging</Term>, and which way it
                  lands depends entirely on whether the price fell before it rose.
                </p>
              </div>
            )}

            <p className="mt-3 text-xs text-zinc-400">
              Bought at {formatMoney(result.stock.buy_price)} on{" "}
              {formatShortDate(result.stock.bought_on)}, valued at the close on{" "}
              {formatShortDate(result.latest_on)}. What a stock did before tells you nothing about
              what it does next.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
