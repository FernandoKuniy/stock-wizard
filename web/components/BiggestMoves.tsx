import type { BiggestMoves as Moves, DayMove } from "@/lib/api";
import { formatPercent, formatShortDate } from "@/lib/format";

/**
 * The handful of days that did most of a stock's moving, with any headlines from those days.
 *
 * The lesson is in the arithmetic: a year of movement lands on a few days out of hundreds,
 * which is why sitting still tends to beat jumping in and out. That is stated as a fact about
 * this stock's own history, not as something to do about it.
 *
 * Most days have no headline, and the copy says so rather than implying the ones that do are
 * the explanation. Every figure comes from services/analysis/moves.py.
 */
export function BiggestMoves({ moves }: { moves: Moves }) {
  if (moves.up.length === 0 && moves.down.length === 0) return null;

  return (
    <div className="rounded-xl border border-zinc-200 p-5 dark:border-zinc-800">
      <h2 className="text-sm font-medium">The days that did the moving</h2>
      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
        Out of {moves.trading_days} trading days, these are the ones that moved the most.
      </p>

      <div className="mt-4 grid gap-5 sm:grid-cols-2">
        <Column label="Biggest jumps" days={moves.up} tone="text-green-600" />
        <Column label="Biggest drops" days={moves.down} tone="text-red-600" />
      </div>

      <p className="mt-4 text-xs text-zinc-400">
        A year of movement usually lands on a handful of days like these, and nobody knows which
        ones they&apos;ll be in advance. Where a day has a headline it&apos;s shown, but plenty of
        big days have no reason you can point at.
      </p>
    </div>
  );
}

function Column({ label, days, tone }: { label: string; days: DayMove[]; tone: string }) {
  return (
    <div>
      <h3 className="text-xs font-medium text-zinc-500">{label}</h3>
      {days.length === 0 ? (
        <p className="mt-2 text-sm text-zinc-400">None over this stretch.</p>
      ) : (
        <ul className="mt-2 space-y-2.5">
          {days.map((day) => (
            <li key={day.date}>
              <div className="flex items-baseline gap-2">
                <span className={`text-sm font-medium tabular-nums ${tone}`}>
                  {formatPercent(day.percent_change)}
                </span>
                <span className="text-xs text-zinc-500">{formatShortDate(day.date)}</span>
              </div>
              {day.news.length > 0 && (
                <a
                  href={day.news[0].url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-0.5 block text-xs text-zinc-500 hover:underline"
                >
                  {day.news[0].headline}
                </a>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
