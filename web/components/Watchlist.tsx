"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { removeFromWatchlist, type WatchlistItem } from "@/lib/api";
import { formatMoney, formatPercent } from "@/lib/format";
import { getAccessToken } from "@/lib/supabase/client";

/**
 * The dashboard's watchlist: stocks the user is tracking without owning. Adding happens on
 * the stock page (the Watch button); here they see the list with a live price and can prune
 * it. Nothing here touches money, so the numbers are just a live quote per row.
 */
export function Watchlist({ items }: { items: WatchlistItem[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function remove(symbol: string) {
    setBusy(symbol);
    setError(null);
    try {
      await removeFromWatchlist(symbol, await getAccessToken());
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't update your watchlist.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="rounded-xl border border-zinc-200 dark:border-zinc-800">
      <div className="flex items-center justify-between border-b border-zinc-100 px-4 py-3 dark:border-zinc-800">
        <h2 className="text-sm font-medium">Watching</h2>
        <span className="text-xs text-zinc-500">
          {items.length} {items.length === 1 ? "stock" : "stocks"}
        </span>
      </div>
      <ul>
        {items.map((item) => {
          const up = (item.percent_change ?? 0) >= 0;
          return (
            <li
              key={item.symbol}
              className="flex items-center justify-between gap-3 border-b border-zinc-50 px-4 py-3 last:border-0 dark:border-zinc-900"
            >
              <Link href={`/stock/${item.symbol}`} className="font-medium hover:underline">
                {item.symbol}
              </Link>
              <div className="flex items-center gap-4">
                <div className="text-right tabular-nums">
                  {item.price === null ? (
                    <span className="text-sm text-zinc-400">price unavailable</span>
                  ) : (
                    <>
                      <div className="text-sm">{formatMoney(item.price)}</div>
                      {item.percent_change !== null && (
                        <div className={`text-xs ${up ? "text-green-600" : "text-red-600"}`}>
                          {formatPercent(item.percent_change)} today
                        </div>
                      )}
                    </>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => void remove(item.symbol)}
                  disabled={busy === item.symbol}
                  aria-label={`Stop watching ${item.symbol}`}
                  className="rounded-md px-2 py-1 text-lg leading-none text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700 disabled:opacity-50 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
                >
                  ×
                </button>
              </div>
            </li>
          );
        })}
      </ul>
      {error && <p className="px-4 py-2 text-xs text-red-500">{error}</p>}
    </section>
  );
}
