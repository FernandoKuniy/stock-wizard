import Link from "next/link";

import { Achievements } from "@/components/Achievements";
import { AllocationChart } from "@/components/AllocationChart";
import { FirstTimeCallout } from "@/components/FirstTimeCallout";
import { HoldingsTable } from "@/components/HoldingsTable";
import { OpenOrders } from "@/components/OpenOrders";
import { PerformanceChart } from "@/components/PerformanceChart";
import { PortfolioSummary } from "@/components/PortfolioSummary";
import { ResetButton } from "@/components/ResetButton";
import { Tutor } from "@/components/Tutor";
import { Watchlist } from "@/components/Watchlist";
import {
  getOrders,
  getPortfolio,
  getPortfolioHistory,
  getWatchlist,
  type Order,
  type Portfolio,
  type PortfolioHistory,
  type WatchlistItem,
} from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { getAccessToken } from "@/lib/supabase/server";

// The portfolio is live data, so render on every request rather than at build.
export const dynamic = "force-dynamic";

export default async function Home() {
  const token = await getAccessToken();

  let portfolio: Portfolio;
  try {
    portfolio = await getPortfolio(token);
  } catch (e) {
    return (
      <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-10">
        <p className="text-sm text-red-500">
          {e instanceof Error ? e.message : "Couldn't load your portfolio."}
        </p>
      </main>
    );
  }

  // The chart is the nice-to-have here. If the market data is having a bad day, the rest of
  // the dashboard still has to work, so a failure here is not a failure of the page.
  let history: PortfolioHistory | null = null;
  try {
    history = await getPortfolioHistory(token);
  } catch {
    history = null;
  }

  // The portfolio call above already settled any limit order whose price arrived, so this
  // just reads the result. Sequential on purpose: two sweeps at once would be wasted work.
  let orders: Order[] = [];
  try {
    orders = await getOrders(token);
  } catch {
    orders = [];
  }

  // The watchlist is a side panel, not the point of the page, so a failure here just hides
  // it rather than breaking the dashboard.
  let watchlist: WatchlistItem[] = [];
  try {
    watchlist = await getWatchlist(token);
  } catch {
    watchlist = [];
  }

  const hasHoldings = portfolio.holdings.length > 0;

  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-10">
      <div className="space-y-6">
        <div className="flex items-start justify-between gap-4">
          <h1 className="text-2xl font-semibold tracking-tight">Your portfolio</h1>
          <ResetButton />
        </div>

        <FirstTimeCallout id="welcome" title="None of this is real money">
          You&apos;ve got {formatMoney(portfolio.starting_balance)} of fake cash and real market
          prices. Buy things, get them wrong, hit reset. That&apos;s the whole point.
        </FirstTimeCallout>

        <PortfolioSummary portfolio={portfolio} />

        {portfolio.unpriced_symbols.length > 0 && (
          <p className="rounded-lg border border-amber-200 bg-amber-50/60 px-4 py-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300">
            We couldn&apos;t get a live price for {portfolio.unpriced_symbols.join(", ")} just now,
            so it&apos;s counted at what you paid. Your totals are a little stale, not wrong.
          </p>
        )}

        {history && <PerformanceChart history={history} />}

        {history?.comparison && (
          <FirstTimeCallout id="benchmark" title="Why the second line matters">
            The grey line is what would have happened if you&apos;d skipped picking stocks and put
            everything into the S&P 500, a basket of 500 big US companies. Most people who pick
            their own stocks do worse than that line. Beating it is the actual game.
          </FirstTimeCallout>
        )}

        {hasHoldings ? (
          <>
            <AllocationChart portfolio={portfolio} />
            <HoldingsTable holdings={portfolio.holdings} />
          </>
        ) : (
          <div className="rounded-xl border border-dashed border-zinc-300 p-8 text-center dark:border-zinc-700">
            <p className="text-lg font-medium">
              You&apos;ve got {formatMoney(portfolio.cash)} to invest.
            </p>
            <p className="mt-1 text-sm text-zinc-500">
              Your holdings will show up here once you buy your first stock.
            </p>
          </div>
        )}

        {orders.length > 0 && <OpenOrders orders={orders} />}

        {watchlist.length > 0 && (
          <>
            <FirstTimeCallout id="watchlist" title="Your watchlist">
              These are stocks you&apos;re keeping an eye on. Adding one costs nothing and
              doesn&apos;t buy anything. Open a stock and hit Watch to track it here.
            </FirstTimeCallout>
            <Watchlist items={watchlist} />
          </>
        )}

        <FirstTimeCallout id="achievements" title="Badges for good habits">
          These aren&apos;t about trading more or beating the market. They mark habits that tend to
          work out, like spreading your money around and sitting tight through a rough patch.
          There&apos;s no streak to keep and nothing to chase. Tap one to read why it matters.
        </FirstTimeCallout>
        <Achievements items={portfolio.achievements} />

        <Tutor />

        <div>
          <Link href="/transactions" className="text-sm text-zinc-500 hover:underline">
            See your transaction history →
          </Link>
        </div>
      </div>

      <p className="mt-10 text-center text-xs text-zinc-500">
        Simulation for education. Not financial advice.
      </p>
    </main>
  );
}
