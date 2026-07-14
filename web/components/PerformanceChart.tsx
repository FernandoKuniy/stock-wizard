"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { PortfolioHistory } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { Term } from "./Term";

// Your money is the one with the colour. The market is the neutral line you're measured
// against, which is exactly the relationship we want people to read off the chart.
const YOU_COLOR = "#6366f1";
const MARKET_COLOR = "#a1a1aa";

export function PerformanceChart({ history }: { history: PortfolioHistory }) {
  const { points, comparison, starting_balance } = history;
  if (points.length < 2) return null;

  const hasBenchmark = comparison !== null;

  return (
    <div className="rounded-xl border border-zinc-200 p-5 dark:border-zinc-800">
      <h2 className="text-sm font-medium text-zinc-500">
        You vs the <Term name="S&P 500">market</Term>
      </h2>

      {comparison && (
        <>
          <p className="mt-1 text-lg font-medium">{headline(comparison.difference)}</p>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            You turned {formatMoney(starting_balance)} into{" "}
            {formatMoney(comparison.portfolio_value)}. Putting all of it into the S&P 500 on day one
            would have made it {formatMoney(comparison.benchmark_value)}.
          </p>
        </>
      )}

      <div className="mt-4 h-64 w-full">
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
      </div>

      <div className="mt-3 flex items-center gap-4 text-xs text-zinc-500">
        <Legend color={YOU_COLOR} label="You" />
        {hasBenchmark ? (
          <Legend color={MARKET_COLOR} label="S&P 500" dashed />
        ) : (
          <span>The S&P 500 comparison isn&apos;t available right now.</span>
        )}
      </div>
    </div>
  );
}

/** The one sentence that answers "how am I actually doing?" */
function headline(difference: number): string {
  if (Math.abs(difference) < 1) return "You're neck and neck with the market.";
  if (difference > 0) {
    return `You're beating the market by ${formatMoney(difference)}.`;
  }
  return `The market is beating you by ${formatMoney(Math.abs(difference))}.`;
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
