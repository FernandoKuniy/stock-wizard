import Link from "next/link";

import type { Holding } from "@/lib/api";
import { formatMoney, formatPercent, formatShares, formatSignedMoney } from "@/lib/format";

export function HoldingsTable({ holdings }: { holdings: Holding[] }) {
  return (
    <div className="overflow-hidden rounded-xl border border-zinc-200 dark:border-zinc-800">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-100 text-left text-zinc-500 dark:border-zinc-800">
              <th className="px-4 py-3 font-medium">Stock</th>
              <th className="px-4 py-3 text-right font-medium">Shares</th>
              <th className="px-4 py-3 text-right font-medium">Price</th>
              <th className="px-4 py-3 text-right font-medium">Value</th>
              <th className="px-4 py-3 text-right font-medium">Gain/loss</th>
            </tr>
          </thead>
          <tbody>
            {holdings.map((holding) => (
              <tr
                key={holding.symbol}
                className="border-b border-zinc-50 last:border-0 dark:border-zinc-900"
              >
                <td className="px-4 py-3">
                  <Link href={`/stock/${holding.symbol}`} className="font-medium hover:underline">
                    {holding.symbol}
                  </Link>
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {formatShares(holding.quantity)}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {holding.price === null ? "—" : formatMoney(holding.price)}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {holding.market_value === null ? "—" : formatMoney(holding.market_value)}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {holding.gain_loss === null || holding.gain_loss_percent === null ? (
                    <span className="text-zinc-400">price unavailable</span>
                  ) : (
                    <span className={holding.gain_loss >= 0 ? "text-green-600" : "text-red-600"}>
                      {formatSignedMoney(holding.gain_loss)} (
                      {formatPercent(holding.gain_loss_percent)})
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
