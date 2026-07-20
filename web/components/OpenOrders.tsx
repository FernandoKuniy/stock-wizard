"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { cancelOrder, type Order } from "@/lib/api";
import { formatMoney, formatShares } from "@/lib/format";
import { getAccessToken } from "@/lib/supabase/client";

// How many finished orders to keep on screen. Enough to see what happened while you were
// away, not so many that the dashboard turns into a ledger.
const RECENT_LIMIT = 3;

/**
 * Limit orders on the dashboard: the ones still waiting, with a way to call them off, and a
 * short tail of ones that recently filled or were cancelled.
 *
 * The copy is deliberately upfront that orders are only checked when the user loads a page.
 * A real broker watches the market non-stop; this one doesn't, and pretending otherwise
 * would be teaching the wrong thing.
 */
export function OpenOrders({ orders }: { orders: Order[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const open = orders.filter((order) => order.status === "open");
  const recent = orders.filter((order) => order.status !== "open").slice(0, RECENT_LIMIT);

  async function cancel(id: number) {
    setBusy(id);
    setError(null);
    try {
      await cancelOrder(id, await getAccessToken());
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't cancel that order.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="rounded-xl border border-zinc-200 dark:border-zinc-800">
      <div className="flex items-center justify-between border-b border-zinc-100 px-4 py-3 dark:border-zinc-800">
        <h2 className="text-sm font-medium">Waiting orders</h2>
        <span className="text-xs text-zinc-500">{open.length} waiting</span>
      </div>

      {open.length > 0 ? (
        <ul>
          {open.map((order) => (
            <li
              key={order.id}
              className="flex items-center justify-between gap-3 border-b border-zinc-50 px-4 py-3 last:border-0 dark:border-zinc-900"
            >
              <div className="text-sm">
                <Link href={`/stock/${order.symbol}`} className="font-medium hover:underline">
                  {order.symbol}
                </Link>
                <span className="ml-2 text-zinc-500">
                  {order.side === "buy" ? "Buy" : "Sell"} {formatShares(order.quantity)} if it{" "}
                  {order.side === "buy" ? "drops to" : "rises to"} {formatMoney(order.limit_price)}
                </span>
              </div>
              <button
                type="button"
                onClick={() => void cancel(order.id)}
                disabled={busy === order.id}
                className="shrink-0 rounded-md px-2 py-1 text-xs text-zinc-500 hover:bg-zinc-100 hover:text-zinc-800 disabled:opacity-50 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
              >
                {busy === order.id ? "Cancelling…" : "Cancel"}
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="px-4 py-3 text-sm text-zinc-500">Nothing waiting right now.</p>
      )}

      {recent.length > 0 && (
        <div className="border-t border-zinc-100 px-4 py-3 dark:border-zinc-800">
          <div className="text-xs text-zinc-400">Recently</div>
          <ul className="mt-2 space-y-1.5">
            {recent.map((order) => (
              <li key={order.id} className="text-xs text-zinc-500">
                <span className={order.status === "filled" ? "text-green-600" : "text-zinc-400"}>
                  {order.status === "filled" ? "Filled" : "Cancelled"}
                </span>{" "}
                {order.side} {formatShares(order.quantity)} {order.symbol} at{" "}
                {formatMoney(order.limit_price)}
                {order.cancel_reason && ` — ${order.cancel_reason}`}
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="border-t border-zinc-100 px-4 py-2 text-xs text-zinc-400 dark:border-zinc-800">
        We check these when you open your dashboard, not every second.
      </p>
      {error && <p className="px-4 pb-2 text-xs text-red-500">{error}</p>}
    </section>
  );
}
