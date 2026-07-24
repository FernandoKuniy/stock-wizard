"use client";

import { useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { getPortfolioHistory, type HistoryPeriod, type PortfolioHistory } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { getAccessToken } from "@/lib/supabase/client";
import { NeverSoldNote } from "./NeverSoldNote";
import { Term } from "./Term";

// Your money is the one with the colour. The market is the neutral line you're measured
// against, which is exactly the relationship we want people to read off the chart.
const YOU_COLOR = "#6366f1";
const MARKET_COLOR = "#a1a1aa";

// Nothing shorter than a month, deliberately. A day-by-day view of your own money is what
// makes people trade on noise, which is the exact habit this chart exists to warn about.
const PERIODS: { value: HistoryPeriod; label: string; phrase: string }[] = [
  { value: "1m", label: "1M", phrase: "A month ago" },
  { value: "6m", label: "6M", phrase: "Six months ago" },
  { value: "1y", label: "1Y", phrase: "A year ago" },
  { value: "all", label: "All", phrase: "When you started" },
];

/**
 * Your money against the index, over a stretch you pick.
 *
 * Switching periods refetches, and costs no market-data call: the backend rebuilds the series
 * over the whole account either way, off candles it already cached, and slices it. Both lines
 * always start at the same number, so the comparison stays honest at any period. Every figure
 * comes from the backend; nothing here does money math.
 */
export function PerformanceChart({ initial }: { initial: PortfolioHistory }) {
  const [history, setHistory] = useState(initial);
  const [period, setPeriod] = useState<HistoryPeriod>(initial.period);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Not enough of a line to draw at all, which means a brand new account. The pills would
  // have nothing to switch between, so show nothing rather than an empty box.
  if (initial.points.length < 2) return null;

  function onPeriodChange(next: HistoryPeriod) {
    setPeriod(next);
    setBusy(true);
    setError(null);
    getAccessToken()
      .then((token) => getPortfolioHistory(token, next))
      .then((data) => setHistory(data))
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : "Couldn't load that stretch.");
      })
      .finally(() => setBusy(false));
  }

  const { points, comparison, baseline } = history;
  const hasBenchmark = comparison !== null;
  const whole = history.period === "all";
  const phrase = PERIODS.find((p) => p.value === history.period)?.phrase ?? "When you started";

  return (
    <div className="rounded-xl border border-zinc-200 p-5 dark:border-zinc-800">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h2 className="text-sm font-medium text-zinc-500">
          You vs the <Term name="S&P 500">market</Term>
        </h2>
        <div className="flex gap-1 text-xs">
          {PERIODS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => onPeriodChange(option.value)}
              aria-pressed={period === option.value}
              className={`rounded-full px-2.5 py-1 ${
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

      {comparison && (
        <>
          <p className="mt-1 text-lg font-medium">{headline(comparison.difference, whole)}</p>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            {phrase} you had {formatMoney(baseline)}. Now you&apos;ve got{" "}
            {formatMoney(comparison.portfolio_value)}. Putting all of it into the S&P 500 back then
            would have made it {formatMoney(comparison.benchmark_value)}.
          </p>
        </>
      )}

      {error && <p className="mt-2 text-sm text-red-500">{error}</p>}

      <div className={`mt-4 h-64 w-full ${busy ? "opacity-50" : ""}`}>
        {points.length < 2 ? (
          <p className="text-sm text-zinc-500">
            Your account isn&apos;t old enough for that stretch yet.
          </p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="currentColor"
                className="text-zinc-100 dark:text-zinc-800"
                vertical={false}
              />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11 }}
                stroke="#a1a1aa"
                tickFormatter={shortDate}
                minTickGap={40}
              />
              <YAxis
                domain={["auto", "auto"]}
                tick={{ fontSize: 11 }}
                stroke="#a1a1aa"
                width={64}
                tickFormatter={(value) => formatMoney(Number(value)).replace(/\.00$/, "")}
              />
              <Tooltip
                formatter={(value, name) => [formatMoney(Number(value)), String(name)]}
                labelFormatter={(label) => longDate(String(label))}
              />
              <Line
                type="monotone"
                dataKey="portfolio"
                name="You"
                stroke={YOU_COLOR}
                strokeWidth={2}
                dot={false}
              />
              {hasBenchmark && (
                <Line
                  type="monotone"
                  dataKey="benchmark"
                  name="S&P 500"
                  stroke={MARKET_COLOR}
                  strokeWidth={2}
                  strokeDasharray="4 4"
                  dot={false}
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="mt-3 flex items-center gap-4 text-xs text-zinc-500">
        <Legend color={YOU_COLOR} label="You" />
        {hasBenchmark ? (
          <Legend color={MARKET_COLOR} label="S&P 500" dashed />
        ) : (
          <span>The S&P 500 comparison isn&apos;t available right now.</span>
        )}
      </div>

      {/* Whole-life only, and only once something has actually been sold. The backend
          decides both, so this just renders whatever came back. */}
      {history.never_sold && points.length > 0 && (
        <NeverSoldNote
          never_sold={history.never_sold}
          actual={points[points.length - 1].portfolio}
        />
      )}
    </div>
  );
}

/** The one sentence that answers "how am I actually doing?" */
function headline(difference: number, whole: boolean): string {
  const over = whole ? "" : "Over this stretch, ";
  if (Math.abs(difference) < 1) return `${over}you're neck and neck with the market.`;
  if (difference > 0) return `${over}you're beating the market by ${formatMoney(difference)}.`;
  return `${over}the market is beating you by ${formatMoney(Math.abs(difference))}.`;
}

function Legend({ color, label, dashed }: { color: string; label: string; dashed?: boolean }) {
  return (
    <span className="flex items-center gap-2">
      <span
        className="inline-block h-0.5 w-5"
        style={
          dashed
            ? {
                backgroundImage: `repeating-linear-gradient(90deg, ${color} 0 4px, transparent 4px 8px)`,
              }
            : { backgroundColor: color }
        }
      />
      {label}
    </span>
  );
}

function shortDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

function longDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}
