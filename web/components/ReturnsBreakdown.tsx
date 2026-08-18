import type { Portfolio } from "@/lib/api";
import { formatSignedMoney } from "@/lib/format";
import { ExplainButton } from "./ExplainButton";
import { Term } from "./Term";

/**
 * Splits the account's total gain into where it came from: money locked in by selling, gain
 * still on paper, and dividends. It's the same total as the overview, shown as its parts, so a
 * beginner can tell what they've actually banked from what's only on screen. Every figure is
 * computed server-side; this only lays them out (hard rule #1), and it explains, never advises.
 */
export function ReturnsBreakdown({ portfolio }: { portfolio: Portfolio }) {
  const { realized_gain, unrealized_gain, dividend_income } = portfolio;

  return (
    <div className="rounded-xl border border-zinc-200 p-5 dark:border-zinc-800">
      <h2 className="text-sm font-medium">Where your gain comes from</h2>
      <div className="mt-3 divide-y divide-zinc-100 dark:divide-zinc-800">
        <Row
          label={<Term name="realized gain">Locked in</Term>}
          amount={realized_gain}
          note="money you've banked by selling"
        />
        <Row
          label={<Term name="unrealized gain">On paper</Term>}
          amount={unrealized_gain}
          note="still riding on what you hold"
        />
        <Row label="Dividends" amount={dividend_income} note="paid to you just for holding" />
      </div>
      <div className="mt-3">
        <ExplainButton prompt="How does my total gain break down into what I've locked in, what's still on paper, and dividends?" />
      </div>
    </div>
  );
}

function Row({ label, amount, note }: { label: React.ReactNode; amount: number; note: string }) {
  // Dividends are never negative, so they read plainly; realized and unrealized get the
  // green/up, red/down treatment the rest of the app uses for money made and lost.
  const color = amount > 0 ? "text-green-600" : amount < 0 ? "text-red-600" : "text-zinc-500";
  return (
    <div className="flex items-baseline justify-between gap-4 py-2">
      <div>
        <div className="text-sm">{label}</div>
        <div className="text-xs text-zinc-500">{note}</div>
      </div>
      <div className={`calm shrink-0 text-sm font-medium tabular-nums ${color}`}>
        {formatSignedMoney(amount)}
      </div>
    </div>
  );
}
