import type { Portfolio } from "@/lib/api";
import { formatMoney, formatPercent, formatSignedMoney } from "@/lib/format";

export function PortfolioSummary({ portfolio }: { portfolio: Portfolio }) {
  const gain = portfolio.total_gain_loss;
  const up = gain >= 0;
  const framing =
    gain === 0
      ? "You're right where you started."
      : up
        ? `You're up ${formatMoney(gain)} since you started.`
        : `You're down ${formatMoney(Math.abs(gain))} since you started.`;

  return (
    <div className="rounded-xl border border-zinc-200 p-5 dark:border-zinc-800">
      <div className="text-sm text-zinc-500">Total value</div>
      <div className="mt-1 text-4xl font-semibold tabular-nums">
        {formatMoney(portfolio.total_value)}
      </div>
      <div className={`mt-1 text-sm tabular-nums ${up ? "text-green-600" : "text-red-600"}`}>
        {formatSignedMoney(gain)} ({formatPercent(portfolio.total_gain_loss_percent)})
      </div>
      <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">{framing}</p>
      <div className="mt-4 grid grid-cols-2 gap-4 border-t border-zinc-100 pt-4 text-sm dark:border-zinc-800">
        <div>
          <div className="text-zinc-500">Cash to invest</div>
          <div className="mt-0.5 font-medium tabular-nums">{formatMoney(portfolio.cash)}</div>
        </div>
        <div>
          <div className="text-zinc-500">Started with</div>
          <div className="mt-0.5 font-medium tabular-nums">
            {formatMoney(portfolio.starting_balance)}
          </div>
        </div>
      </div>
    </div>
  );
}
