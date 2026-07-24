import Link from "next/link";

import { AllocationChart } from "@/components/AllocationChart";
import { Checkup } from "@/components/Checkup";
import { FirstTimeCallout } from "@/components/FirstTimeCallout";
import { HoldingsTable } from "@/components/HoldingsTable";
import { getCheckup, getPortfolio, type CheckupFinding, type Portfolio } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { getAccessToken } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

/**
 * Everything you own, in full: how it's split up, and how each position is doing.
 *
 * Only fetches the portfolio. The performance history is the expensive call (one candle
 * request per symbol ever held, against a free tier of 8 a minute) and it lives on the
 * overview, so coming here to inspect a position doesn't pay for a chart you can't see.
 */
export default async function HoldingsPage() {
  const token = await getAccessToken();

  let portfolio: Portfolio;
  try {
    portfolio = await getPortfolio(token);
  } catch (e) {
    return (
      <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-10">
        <p className="text-sm text-red-500">
          {e instanceof Error ? e.message : "Couldn't load your holdings."}
        </p>
      </main>
    );
  }

  // The check-up is a read on what's already here, so a failure just hides it rather than
  // taking the page down with it.
  let checkup: CheckupFinding[] = [];
  try {
    checkup = await getCheckup(token);
  } catch {
    checkup = [];
  }

  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-10">
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight">What you own</h1>

        {portfolio.holdings.length > 0 ? (
          <>
            {portfolio.unpriced_symbols.length > 0 && (
              <p className="rounded-lg border border-amber-200 bg-amber-50/60 px-4 py-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300">
                We couldn&apos;t get a live price for {portfolio.unpriced_symbols.join(", ")} just
                now, so it&apos;s counted at what you paid. Your totals are a little stale, not
                wrong.
              </p>
            )}
            {checkup.length > 0 && (
              <FirstTimeCallout id="checkup" title="A read on how it's spread">
                These are just observations about what you own, worked out from your own holdings.
                Nothing here is telling you to buy or sell anything. Tap one to read why it matters.
              </FirstTimeCallout>
            )}
            <Checkup findings={checkup} />
            <AllocationChart portfolio={portfolio} />
            <HoldingsTable holdings={portfolio.holdings} />
          </>
        ) : (
          <div className="rounded-xl border border-dashed border-zinc-300 p-8 text-center dark:border-zinc-700">
            <p className="text-lg font-medium">Nothing here yet.</p>
            <p className="mt-1 text-sm text-zinc-500">
              You&apos;ve got {formatMoney(portfolio.cash)} to invest. Search for a company up top
              to see its price and buy some.
            </p>
            <Link href="/" className="mt-4 inline-block text-sm text-zinc-500 hover:underline">
              Back to the overview →
            </Link>
          </div>
        )}
      </div>

      <p className="mt-10 text-center text-xs text-zinc-500">
        Simulation for education. Not financial advice.
      </p>
    </main>
  );
}
