import type { NeverSold } from "@/lib/api";
import { formatMoney } from "@/lib/format";

/**
 * "What if you'd never sold?" replayed from the account's own buys at today's prices.
 *
 * This is a fact about what already happened, not a lesson and not a nudge. It comes out the
 * other way often enough (selling before a drop is a real thing), which is exactly why it can
 * be shown at all: it teaches that trading has an outcome you can measure, without implying
 * which outcome you were supposed to get. The caveat under it is not decoration.
 *
 * Only appears on the whole-life view, and only once the account has actually sold something.
 * Every figure is computed by services/analysis/history.py.
 */
export function NeverSoldNote({ never_sold, actual }: { never_sold: NeverSold; actual: number }) {
  const { value, difference } = never_sold;
  const same = Math.abs(difference) < 1;

  return (
    <div className="mt-4 rounded-lg border border-zinc-100 bg-zinc-50/60 px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900/40">
      {/* The whole sentence blurs under calm mode: it's figures end to end, with no direction
          word worth keeping on its own. */}
      <p className="calm text-sm text-zinc-700 dark:text-zinc-300">
        {same ? (
          <>
            If you&apos;d never sold anything, you&apos;d have about what you&apos;ve got now,{" "}
            {formatMoney(value)}.
          </>
        ) : (
          <>
            If you&apos;d never sold anything, you&apos;d have {formatMoney(value)} right now
            instead of {formatMoney(actual)}.{" "}
            {difference > 0 ? (
              <>Selling has worked out so far, by {formatMoney(difference)}.</>
            ) : (
              <>That&apos;s {formatMoney(Math.abs(difference))} more than you&apos;ve got.</>
            )}
          </>
        )}
      </p>
      <p className="mt-1.5 text-xs text-zinc-400">
        This just replays your own buys at today&apos;s prices. It doesn&apos;t mean selling was the
        wrong call, and it says nothing about what happens next.
      </p>
    </div>
  );
}
