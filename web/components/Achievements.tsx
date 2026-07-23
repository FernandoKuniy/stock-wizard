import { type Achievement } from "@/lib/api";
import { formatShortDate } from "@/lib/format";

/**
 * The dashboard's habit badges. Earned ones are lit; still-locked ones stay dimmed and show
 * how to earn them, so the list doubles as a few good habits to aim for.
 *
 * These reward habits, never activity or profit (see docs/decisions.md): the point is to
 * teach, not to pull people back to check their money daily. So there's no streak counter and
 * no "you're on fire" nudging. Each badge just opens a short explainer, which is the actual
 * product. Every badge is named for the fact it marks, not for praise.
 *
 * Uses a native <details> so it expands with no client-side JS.
 */
export function Achievements({ items }: { items: Achievement[] }) {
  const earnedCount = items.filter((item) => item.earned).length;

  return (
    <section className="rounded-xl border border-zinc-200 dark:border-zinc-800">
      <div className="flex items-center justify-between border-b border-zinc-100 px-4 py-3 dark:border-zinc-800">
        <h2 className="text-sm font-medium">Good habits</h2>
        <span className="text-xs text-zinc-500">
          {earnedCount} of {items.length}
        </span>
      </div>

      <ul>
        {items.map((item) => (
          <li key={item.key} className="border-b border-zinc-50 last:border-0 dark:border-zinc-900">
            <details className="group">
              <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-3 [&::-webkit-details-marker]:hidden">
                <span
                  aria-hidden
                  className={`flex size-6 shrink-0 items-center justify-center rounded-full text-xs ${
                    item.earned
                      ? "bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300"
                      : "bg-zinc-100 text-zinc-400 dark:bg-zinc-800 dark:text-zinc-500"
                  }`}
                >
                  {item.earned ? "✓" : "○"}
                </span>
                <div className="min-w-0 flex-1">
                  <div
                    className={`text-sm ${
                      item.earned ? "font-medium" : "text-zinc-500 dark:text-zinc-400"
                    }`}
                  >
                    {item.title}
                  </div>
                  <div className="text-xs text-zinc-400">
                    {item.earned && item.earned_at
                      ? `Earned ${formatShortDate(item.earned_at.slice(0, 10))}`
                      : item.requirement}
                  </div>
                </div>
                <span className="shrink-0 text-xs text-zinc-400 transition-transform group-open:rotate-180">
                  ⌄
                </span>
              </summary>
              <p className="px-4 pb-3 pl-13 text-sm text-zinc-600 dark:text-zinc-300">
                {item.lesson}
              </p>
            </details>
          </li>
        ))}
      </ul>

      <p className="border-t border-zinc-100 px-4 py-2 text-xs text-zinc-400 dark:border-zinc-800">
        These reward habits, not trading. There&apos;s nothing to keep a streak going.
      </p>
    </section>
  );
}
