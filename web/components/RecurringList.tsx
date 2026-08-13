"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { deleteRecurring, updateRecurring, type Recurring } from "@/lib/api";
import { formatMoney, formatShortDate } from "@/lib/format";
import { getAccessToken } from "@/lib/supabase/client";

/** The account's automatic investments, with pause/resume and cancel. */
export function RecurringList({ items }: { items: Recurring[] }) {
  if (items.length === 0) return null;
  return (
    <div className="space-y-3">
      {items.map((item) => (
        <RecurringRow key={item.id} item={item} />
      ))}
    </div>
  );
}

function RecurringRow({ item }: { item: Recurring }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const every = item.cadence === "monthly" ? "month" : "week";

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "That didn't work.");
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm">
            <span className="font-medium tabular-nums">{formatMoney(item.amount)}</span> into{" "}
            <Link href={`/stock/${item.symbol}`} className="font-medium hover:underline">
              {item.symbol}
            </Link>{" "}
            every {every}
          </div>
          <div className="mt-1 text-xs text-zinc-500">
            {item.active ? (
              <>Next on {formatShortDate(item.next_run_on)}</>
            ) : (
              <span className="text-amber-600">Paused</span>
            )}
            {item.last_run_on && <> · last ran {formatShortDate(item.last_run_on)}</>}
          </div>
          {item.paused_reason && (
            <p className="mt-1 text-xs text-amber-600">{item.paused_reason}</p>
          )}
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void act(async () => updateRecurring(item.id, !item.active, await getAccessToken()))
            }
            className="rounded-lg border border-zinc-300 px-3 py-1 text-xs font-medium hover:bg-zinc-50 disabled:opacity-40 dark:border-zinc-700 dark:hover:bg-zinc-900"
          >
            {item.active ? "Pause" : "Resume"}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void act(async () => deleteRecurring(item.id, await getAccessToken()))}
            className="rounded-lg px-3 py-1 text-xs font-medium text-zinc-500 hover:text-red-600 disabled:opacity-40"
          >
            Cancel
          </button>
        </div>
      </div>
      {error && <p className="mt-2 text-xs text-red-500">{error}</p>}
    </div>
  );
}
