import Link from "next/link";

import type { Dividend } from "@/lib/api";
import { formatMoney, formatShares, formatShortDate } from "@/lib/format";

/** Dividends the account has been paid for holding its stocks, newest ex-date first. */
export function DividendsList({ dividends }: { dividends: Dividend[] }) {
  if (dividends.length === 0) return null;

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-200 dark:border-zinc-800">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-100 text-left text-zinc-500 dark:border-zinc-800">
              <th className="px-4 py-3 font-medium">Ex-date</th>
              <th className="px-4 py-3 font-medium">Stock</th>
              <th className="px-4 py-3 text-right font-medium">Shares</th>
              <th className="px-4 py-3 text-right font-medium">Per share</th>
              <th className="px-4 py-3 text-right font-medium">Paid you</th>
            </tr>
          </thead>
          <tbody>
            {dividends.map((dividend) => (
              <tr
                key={`${dividend.symbol}-${dividend.ex_date}`}
                className="border-b border-zinc-50 last:border-0 dark:border-zinc-900"
              >
                <td className="px-4 py-3 whitespace-nowrap text-zinc-500">
                  {formatShortDate(dividend.ex_date)}
                </td>
                <td className="px-4 py-3">
                  <Link href={`/stock/${dividend.symbol}`} className="font-medium hover:underline">
                    {dividend.symbol}
                  </Link>
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {formatShares(dividend.shares)}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {formatMoney(dividend.per_share)}
                </td>
                <td className="px-4 py-3 text-right font-medium tabular-nums text-green-600">
                  {formatMoney(dividend.amount)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
