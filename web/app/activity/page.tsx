import { FirstTimeCallout } from "@/components/FirstTimeCallout";
import { OpenOrders } from "@/components/OpenOrders";
import { TransactionsTable } from "@/components/TransactionsTable";
import { Watchlist } from "@/components/Watchlist";
import {
  getOrders,
  getTransactions,
  getWatchlist,
  type Order,
  type Transaction,
  type WatchlistItem,
} from "@/lib/api";
import { getAccessToken } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

/**
 * The moving parts: orders still waiting, stocks you're keeping an eye on, and everything
 * you've already done.
 *
 * Loading the orders settles any resting limit order whose price has arrived, since the app
 * runs no background job. Transactions come after that, so an order that just filled shows
 * up in the history on the same load.
 */
export default async function ActivityPage() {
  const token = await getAccessToken();

  let orders: Order[] = [];
  try {
    orders = await getOrders(token);
  } catch {
    orders = [];
  }

  let transactions: Transaction[] = [];
  let transactionsError: string | null = null;
  try {
    transactions = await getTransactions(token);
  } catch (e) {
    transactionsError = e instanceof Error ? e.message : "Couldn't load your trades.";
  }

  // The watchlist is a side panel, not the point of the page, so a failure here just leaves
  // it empty rather than breaking everything else.
  let watchlist: WatchlistItem[] = [];
  try {
    watchlist = await getWatchlist(token);
  } catch {
    watchlist = [];
  }

  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-10">
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight">Activity</h1>

        <OpenOrders orders={orders} />

        {watchlist.length > 0 ? (
          <>
            <FirstTimeCallout id="watchlist" title="Your watchlist">
              These are stocks you&apos;re keeping an eye on. Adding one costs nothing and
              doesn&apos;t buy anything. Open a stock and hit Watch to track it here.
            </FirstTimeCallout>
            <Watchlist items={watchlist} />
          </>
        ) : (
          <section className="rounded-xl border border-zinc-200 dark:border-zinc-800">
            <div className="border-b border-zinc-100 px-4 py-3 dark:border-zinc-800">
              <h2 className="text-sm font-medium">Watching</h2>
            </div>
            <p className="px-4 py-3 text-sm text-zinc-500">
              Nothing yet. Open a stock and hit Watch to keep an eye on it without buying it.
            </p>
          </section>
        )}

        <section className="space-y-3">
          <h2 className="text-sm font-medium">Everything you&apos;ve done</h2>
          {transactionsError ? (
            <p className="text-sm text-red-500">{transactionsError}</p>
          ) : (
            <TransactionsTable transactions={transactions} />
          )}
        </section>
      </div>

      <p className="mt-10 text-center text-xs text-zinc-500">
        Simulation for education. Not financial advice.
      </p>
    </main>
  );
}
