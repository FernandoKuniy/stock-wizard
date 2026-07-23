import Link from "next/link";

import type { Holding } from "@/lib/api";
import { formatMoney, formatSignedMoney } from "@/lib/format";

// How many positions the overview shows before handing off to the full table.
const SHOWN = 3;

/**
 * A short reminder of what you actually own, for the overview.
 *
 * The point of this strip is that moving the holdings table to its own page shouldn't make
 * anyone wonder where their stocks went. It answers "what have I got?" in three lines and
 * then gets out of the way; the numbers, weights and cost basis live on /holdings.
 */
export function TopHoldings({ holdings }: { holdings: Holding[] }) {
  // Biggest positions first. One we couldn't price sorts last rather than as zero, so a
  // flaky quote never buries a real position at the bottom of the list.
  const ranked = [...holdings].sort((a, b) => (b.market_value ?? -1) - (a.market_value ?? -1));
  const shown = ranked.slice(0, SHOWN);
  const hidden = holdings.length - shown.length;

  return (
    <section className="rounded-xl border border-zinc-200 dark:border-zinc-800">
      <div className="flex items-center justify-between border-b border-zinc-100 px-4 py-3 dark:border-zinc-800">
        <h2 className="text-sm font-medium">What you own</h2>
        <span className="text-xs text-zinc-500">
          {holdings.length} {holdings.length === 1 ? "company" : "companies"}
        </span>
      </div>

      <ul>
        {shown.map((holding) => (
          <li
            key={holding.symbol}
            className="flex items-center justify-between gap-3 border-b border-zinc-50 px-4 py-3 last:border-0 dark:border-zinc-900"
          >
            <Link href={`/stock/${holding.symbol}`} className="font-medium hover:underline">
              {holding.symbol}
            </Link>
            <div className="text-right tabular-nums">
              {holding.market_value === null || holding.gain_loss === null ? (
                <span className="text-sm text-zinc-400">price unavailable</span>
              ) : (
                <>
                  <div className="text-sm">{formatMoney(holding.market_value)}</div>
                  <div
                    className={`text-xs ${
                      holding.gain_loss >= 0 ? "text-green-600" : "text-red-600"
                    }`}
                  >
                    {formatSignedMoney(holding.gain_loss)}
                  </div>
                </>
              )}
            </div>
          </li>
        ))}
      </ul>

      <div className="border-t border-zinc-100 px-4 py-2.5 dark:border-zinc-800">
        <Link href="/holdings" className="text-sm text-zinc-500 hover:underline">
          {hidden > 0 ? `See all ${holdings.length} →` : "See the full breakdown →"}
        </Link>
      </div>
    </section>
  );
}
