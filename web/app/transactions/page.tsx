import Link from "next/link";

import { getTransactions, type Transaction } from "@/lib/api";
import { formatDateTime, formatMoney, formatShares } from "@/lib/format";
import { getAccessToken } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export default async function TransactionsPage() {
  let transactions: Transaction[];
  try {
    transactions = await getTransactions(await getAccessToken());
  } catch (e) {
    return (
      <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-10">
        <Link href="/" className="text-sm text-zinc-500 hover:underline">
          ← Back to portfolio
        </Link>
        <p className="mt-6 text-sm text-red-500">
          {e instanceof Error ? e.message : "Couldn't load your transactions."}
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-10">
      <Link href="/" className="text-sm text-zinc-500 hover:underline">
        ← Back to portfolio
      </Link>
      <h1 className="mt-6 text-2xl font-semibold tracking-tight">Transaction history</h1>

      {transactions.length === 0 ? (
        <p className="mt-6 text-sm text-zinc-500">
          No trades yet. Once you buy or sell, it&apos;ll show up here.
        </p>
      ) : (
        <div className="mt-6 overflow-hidden rounded-xl border border-zinc-200 dark:border-zinc-800">
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
                    <td className="px-4 py-3 text-right tabular-nums">
                      {formatShares(txn.quantity)}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">{formatMoney(txn.price)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{formatMoney(txn.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <p className="mt-10 text-center text-xs text-zinc-500">
        Simulation for education. Not financial advice.
      </p>
    </main>
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
