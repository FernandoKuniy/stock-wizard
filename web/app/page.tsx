import { Achievements } from "@/components/Achievements";
import { FirstTimeCallout } from "@/components/FirstTimeCallout";
import { PerformanceChart } from "@/components/PerformanceChart";
import { PortfolioSummary } from "@/components/PortfolioSummary";
import { ResetButton } from "@/components/ResetButton";
import { StartHere } from "@/components/StartHere";
import { TopHoldings } from "@/components/TopHoldings";
import {
  getPortfolio,
  getPortfolioHistory,
  type Portfolio,
  type PortfolioHistory,
} from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { getAccessToken } from "@/lib/supabase/server";

// The portfolio is live data, so render on every request rather than at build.
export const dynamic = "force-dynamic";

/**
 * The overview. This page answers one question, "how am I doing?", and nothing else.
 *
 * Holdings, orders, the watchlist and your trade history all live on their own pages now.
 * Keeping them off here is the point: someone nervous should be able to log in, read one
 * number and one sentence, and stop.
 */
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
  // the page still has to work, so a failure here is not a failure of the page.
  //
  // Sequential on purpose: the portfolio call above settles any limit order whose price has
  // arrived, and the history is rebuilt from the transactions. Racing them could draw a
  // chart that misses an order that just filled.
  let history: PortfolioHistory | null = null;
  try {
    history = await getPortfolioHistory(token);
  } catch {
    history = null;
  }

  const hasHoldings = portfolio.holdings.length > 0;

  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-10">
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight">How you&apos;re doing</h1>

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

        {history && <PerformanceChart initial={history} />}

        {history?.comparison && (
          <FirstTimeCallout id="benchmark" title="Why the second line matters">
            The grey line is what would have happened if you&apos;d skipped picking stocks and put
            everything into the S&P 500, a basket of 500 big US companies. Most people who pick
            their own stocks do worse than that line. Beating it is the actual game.
          </FirstTimeCallout>
        )}

        {hasHoldings ? (
          <TopHoldings holdings={portfolio.holdings} />
        ) : (
          <StartHere cash={portfolio.cash} />
        )}

        <FirstTimeCallout id="achievements" title="Badges for good habits">
          These aren&apos;t about trading more or beating the market. They mark habits that tend to
          work out, like spreading your money around and sitting tight through a rough patch.
          There&apos;s no streak to keep and nothing to chase. Tap one to read why it matters.
        </FirstTimeCallout>
        <Achievements items={portfolio.achievements} />

        {/* Down here on purpose. The reset button is one of the two things that most reduce
            beginner anxiety, so it stays easy to find, but sitting next to the headline
            number it reads like a warning rather than a safety net. */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-zinc-100 pt-6 dark:border-zinc-800">
          <p className="text-sm text-zinc-500">
            Had enough? Wipe it all and start over with {formatMoney(portfolio.starting_balance)}.
          </p>
          <ResetButton />
        </div>
      </div>

      <p className="mt-10 text-center text-xs text-zinc-500">
        Simulation for education. Not financial advice.
      </p>
    </main>
  );
}
