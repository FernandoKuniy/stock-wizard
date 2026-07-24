"use client";

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import type { Portfolio } from "@/lib/api";
import { formatMoney } from "@/lib/format";

const HOLDING_COLORS = [
  "#6366f1",
  "#22c55e",
  "#f59e0b",
  "#ec4899",
  "#06b6d4",
  "#a855f7",
  "#ef4444",
  "#84cc16",
];
const CASH_COLOR = "#a1a1aa";

type Slice = { name: string; value: number; weight: number; color: string };

export function AllocationChart({ portfolio }: { portfolio: Portfolio }) {
  const slices: Slice[] = [];
  portfolio.holdings.forEach((holding, index) => {
    if (holding.market_value && holding.market_value > 0) {
      slices.push({
        name: holding.symbol,
        value: holding.market_value,
        weight: holding.weight ?? 0,
        color: HOLDING_COLORS[index % HOLDING_COLORS.length],
      });
    }
  });
  if (portfolio.cash > 0) {
    slices.push({
      name: "Cash",
      value: portfolio.cash,
      weight: portfolio.cash_weight,
      color: CASH_COLOR,
    });
  }

  if (slices.length === 0) {
    return null;
  }

  return (
    <div className="rounded-xl border border-zinc-200 p-5 dark:border-zinc-800">
      <h2 className="mb-3 text-sm font-medium text-zinc-500">What you&apos;re holding</h2>
      <div className="flex flex-col items-center gap-5 sm:flex-row">
        {/* Labelled rather than described: the legend beside it already lists every slice
            and its weight as text. */}
        <div
          role="img"
          aria-label="Donut chart of how your money is split up. The same figures are listed beside it."
          className="h-48 w-48 shrink-0"
        >
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={slices}
                dataKey="value"
                nameKey="name"
                innerRadius="62%"
                outerRadius="100%"
                paddingAngle={1}
                stroke="none"
              >
                {slices.map((slice) => (
                  <Cell key={slice.name} fill={slice.color} />
                ))}
              </Pie>
              <Tooltip formatter={(value) => formatMoney(Number(value))} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <ul className="flex-1 space-y-1.5 self-stretch text-sm">
          {slices.map((slice) => (
            <li key={slice.name} className="flex items-center justify-between gap-3">
              <span className="flex items-center gap-2">
                <span
                  className="inline-block h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: slice.color }}
                />
                {slice.name}
              </span>
              <span className="tabular-nums text-zinc-500">{slice.weight.toFixed(1)}%</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
