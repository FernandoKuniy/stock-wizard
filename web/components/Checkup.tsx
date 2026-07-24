import type { CheckupFinding, CheckupStatus } from "@/lib/api";

/**
 * The portfolio check-up: a few plain-English observations about how your money is spread.
 *
 * Every sentence, including the numbers in it, is composed server-side by
 * services/analysis/checkup.py. Nothing here does money math and nothing here writes copy.
 *
 * Amber, never red. Red and green mean "you lost money" and "you made money" everywhere else
 * in this app, and a notable finding is neither: it's something worth understanding, not a
 * mistake. Each row opens its lesson with a native <details>, the same as the habit badges,
 * so it needs no client-side JS.
 */
export function Checkup({ findings }: { findings: CheckupFinding[] }) {
  if (findings.length === 0) return null;

  const notable = findings.filter((finding) => finding.status === "notable").length;

  return (
    <section className="rounded-xl border border-zinc-200 dark:border-zinc-800">
      <div className="flex items-center justify-between gap-3 border-b border-zinc-100 px-4 py-3 dark:border-zinc-800">
        <h2 className="text-sm font-medium">How your money is spread</h2>
        <span className="text-xs text-zinc-500">
          {notable === 0 ? "nothing unusual" : `${notable} worth a look`}
        </span>
      </div>

      <ul>
        {findings.map((finding) => (
          <li
            key={finding.key}
            className="border-b border-zinc-50 last:border-0 dark:border-zinc-900"
          >
            <details className="group">
              <summary className="flex cursor-pointer list-none items-start gap-3 px-4 py-3 [&::-webkit-details-marker]:hidden">
                <StatusDot status={finding.status} />
                <div className="min-w-0 flex-1">
                  <div className="text-sm">{finding.detail}</div>
                  <div className="text-xs text-zinc-400">{finding.title}</div>
                </div>
                <span className="shrink-0 text-xs text-zinc-400 transition-transform group-open:rotate-180">
                  ⌄
                </span>
              </summary>
              <p className="px-4 pb-3 pl-13 text-sm text-zinc-600 dark:text-zinc-300">
                {finding.lesson}
              </p>
            </details>
          </li>
        ))}
      </ul>

      <p className="border-t border-zinc-100 px-4 py-2 text-xs text-zinc-400 dark:border-zinc-800">
        These describe what you own. They&apos;re not telling you to change it.
      </p>
    </section>
  );
}

function StatusDot({ status }: { status: CheckupStatus }) {
  const styles: Record<CheckupStatus, string> = {
    ok: "bg-zinc-100 text-zinc-400 dark:bg-zinc-800 dark:text-zinc-500",
    notable: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
    unknown: "bg-zinc-100 text-zinc-400 dark:bg-zinc-800 dark:text-zinc-500",
  };
  const marks: Record<CheckupStatus, string> = { ok: "✓", notable: "!", unknown: "?" };

  return (
    <span
      aria-hidden
      className={`mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full text-xs ${styles[status]}`}
    >
      {marks[status]}
    </span>
  );
}
