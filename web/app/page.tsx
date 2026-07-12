import Link from "next/link";

import { AllocationChart } from "@/components/AllocationChart";
import { HoldingsTable } from "@/components/HoldingsTable";
import { PortfolioSummary } from "@/components/PortfolioSummary";
import { ResetButton } from "@/components/ResetButton";
import { getPortfolio, type Portfolio } from "@/lib/api";
import { formatMoney } from "@/lib/format";

// The portfolio is live data, so render on every request rather than at build.
export const dynamic = "force-dynamic";

export default async function Home() {
  let portfolio: Portfolio;
  try {
    portfolio = await getPortfolio();
  } catch (e) {
    return (
      <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-10">
        <p className="text-sm text-red-500">
          {e instanceof Error ? e.message : "Couldn't load your portfolio."}
        </p>
      </main>
    );
  }

  const hasHoldings = portfolio.holdings.length > 0;

  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-10">
      <div className="space-y-6">
        <div className="flex items-start justify-between gap-4">
          <h1 className="text-2xl font-semibold tracking-tight">Your portfolio</h1>
          <ResetButton />
        </div>

        <PortfolioSummary portfolio={portfolio} />

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
