import Link from "next/link";

import type { Transaction } from "@/lib/api";
import { formatDateTime, formatMoney, formatShares } from "@/lib/format";

/** Everything you've bought and sold, newest first. */
export function TransactionsTable({ transactions }: { transactions: Transaction[] }) {
  if (transactions.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-zinc-300 px-4 py-6 text-center text-sm text-zinc-500 dark:border-zinc-700">
        No trades yet. Once you buy or sell, it&apos;ll show up here.
      </p>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-200 dark:border-zinc-800">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-100 text-left text-zinc-500 dark:border-zinc-800">
              <th className="px-4 py-3 font-medium">Date</th>
              <th className="px-4 py-3 font-medium">Action</th>
              <th className="px-4 py-3 font-medium">Stock</th>
              <th className="px-4 py-3 text-right font-medium">Shares</th>
              <th className="px-4 py-3 text-right font-medium">Price</th>
              <th className="px-4 py-3 text-right font-medium">Total</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((txn) => (
              <tr
                key={txn.id}
                className="border-b border-zinc-50 last:border-0 dark:border-zinc-900"
              >
                <td className="px-4 py-3 whitespace-nowrap text-zinc-500">
                  {formatDateTime(txn.timestamp)}
                </td>
                <td className="px-4 py-3">
                  <SideBadge side={txn.side} />
                </td>
                <td className="px-4 py-3">
                  <Link href={`/stock/${txn.symbol}`} className="font-medium hover:underline">
                    {txn.symbol}
                  </Link>
                </td>
                <td className="px-4 py-3 text-right tabular-nums">{formatShares(txn.quantity)}</td>
                <td className="px-4 py-3 text-right tabular-nums">{formatMoney(txn.price)}</td>
                <td className="px-4 py-3 text-right tabular-nums">{formatMoney(txn.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SideBadge({ side }: { side: string }) {
  const buy = side === "buy";
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
        buy
          ? "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400"
          : "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400"
      }`}
    >
      {buy ? "Buy" : "Sell"}
    </span>
  );
}
