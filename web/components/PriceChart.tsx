"use client";

import { Line, LineChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";

import type { CandlePoint } from "@/lib/api";
import { formatMoney } from "@/lib/format";

export function PriceChart({ points }: { points: CandlePoint[] }) {
  if (points.length === 0) {
    return null;
  }
  const rising = points[points.length - 1].close >= points[0].close;
  const color = rising ? "#22c55e" : "#ef4444";

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
          <YAxis domain={["auto", "auto"]} hide />
          <Tooltip
            formatter={(value) => [formatMoney(Number(value)), "Close"]}
            labelFormatter={(label) => String(label)}
          />
          <Line type="monotone" dataKey="close" stroke={color} strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
