import type { Portfolio } from "@/lib/api";
import { formatMoney, formatPercent, formatSignedMoney } from "@/lib/format";

export function PortfolioSummary({ portfolio }: { portfolio: Portfolio }) {
  const gain = portfolio.total_gain_loss;
  const up = gain >= 0;

  return (
    <div className="rounded-xl border border-zinc-200 p-5 dark:border-zinc-800">
      <div className="text-sm text-zinc-500">Total value</div>
      {/* `calm` marks a figure the "hide amounts" toggle blurs. The direction words stay
          readable on purpose: knowing you're up or down without the number is the point. */}
      <div className="calm mt-1 text-4xl font-semibold tabular-nums">
        {formatMoney(portfolio.total_value)}
      </div>
      <div className={`mt-1 text-sm tabular-nums ${up ? "text-green-600" : "text-red-600"}`}>
        <span className="calm">
          {formatSignedMoney(gain)} ({formatPercent(portfolio.total_gain_loss_percent)})
        </span>
      </div>
      <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
        {gain === 0 ? (
          "You're right where you started."
        ) : (
          <>
            You&apos;re {up ? "up" : "down"}{" "}
            <span className="calm">{formatMoney(Math.abs(gain))}</span> since you started.
          </>
        )}
      </p>
      {/* Written by the backend, and deliberately a separate sentence from the one above:
          it covers what you're holding right now, while the total also carries money you've
          already banked from things you sold. See services/analysis/movers.py. */}
      {/* The whole line blurs together: it arrives from the backend as one composed sentence,
          so there's no figure inside it to wrap on its own. */}
      {portfolio.what_moved && (
        <p className="calm mt-1 text-sm text-zinc-500">{portfolio.what_moved}</p>
      )}
      <div className="mt-4 grid grid-cols-2 gap-4 border-t border-zinc-100 pt-4 text-sm dark:border-zinc-800">
        <div>
          <div className="text-zinc-500">Cash to invest</div>
          <div className="calm mt-0.5 font-medium tabular-nums">{formatMoney(portfolio.cash)}</div>
        </div>
        <div>
          <div className="text-zinc-500">Started with</div>
          <div className="calm mt-0.5 font-medium tabular-nums">
            {formatMoney(portfolio.starting_balance)}
          </div>
        </div>
      </div>
    </div>
  );
}
