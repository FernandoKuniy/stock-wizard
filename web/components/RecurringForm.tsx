"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { createRecurring, type RecurringCadence } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { getAccessToken } from "@/lib/supabase/client";
import { FirstTimeCallout } from "./FirstTimeCallout";
import { Term } from "./Term";

/**
 * Set up an automatic investment in this stock: the same dollar amount, every week or month.
 *
 * This is the habit the app most wants to teach, made real. The buys settle on the same lazy
 * sweep as a limit order, so nothing happens until the dashboard is next loaded.
 */
export function RecurringForm({ symbol }: { symbol: string }) {
  const router = useRouter();
  const [amount, setAmount] = useState("");
  const [cadence, setCadence] = useState<RecurringCadence>("monthly");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const value = Number(amount);
  const valid = amount.trim() !== "" && Number.isFinite(value) && value > 0;
  const every = cadence === "monthly" ? "month" : "week";

  async function submit() {
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      await createRecurring({ symbol, amount: value, cadence }, await getAccessToken());
      setDone(
        `Set up. ${formatMoney(value)} into ${symbol} every ${every}, starting next time you open your dashboard.`,
      );
      setAmount("");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't set that up.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-4 rounded-xl border border-zinc-200 p-5 dark:border-zinc-800">
      <h2 className="text-sm font-medium">Invest automatically</h2>
      <p className="mt-1 text-xs text-zinc-500">
        Put the same amount into {symbol} on a schedule, hands-off.
      </p>

      <div className="mt-3 flex gap-2 text-xs">
        <button
          type="button"
          onClick={() => setCadence("weekly")}
          className={pill(cadence === "weekly")}
        >
          Weekly
        </button>
        <button
          type="button"
          onClick={() => setCadence("monthly")}
          className={pill(cadence === "monthly")}
        >
          Monthly
        </button>
      </div>

      <label className="mt-3 flex items-center gap-2 rounded-lg border border-zinc-200 px-3 py-2 dark:border-zinc-800">
        <span className="text-zinc-500">$</span>
        <input
          type="text"
          inputMode="decimal"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder="0.00"
          aria-label="Amount to invest each time"
          className="w-full bg-transparent tabular-nums outline-none"
        />
        <span className="shrink-0 text-xs text-zinc-500">every {every}</span>
      </label>

      {valid && (
        <p className="mt-2 text-xs text-zinc-500">
          {formatMoney(value)} into {symbol} every {every}. You can pause or cancel it any time.
        </p>
      )}

      <button
        type="button"
        onClick={() => void submit()}
        disabled={busy || !valid}
        className="mt-4 w-full rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium hover:bg-zinc-50 disabled:opacity-40 dark:border-zinc-700 dark:hover:bg-zinc-900"
      >
        {busy ? "Setting up…" : `Invest every ${every}`}
      </button>

      <div className="mt-4">
        <FirstTimeCallout id="recurring" title="Little and often">
          Putting a fixed amount in on a regular schedule is called{" "}
          <Term name="dollar-cost averaging">dollar-cost averaging</Term>. You buy more shares when
          the price is low and fewer when it&apos;s high, without trying to guess the right moment.
          It runs when you open your dashboard, since the app has no background job.
        </FirstTimeCallout>
      </div>

      {done && <p className="mt-3 text-sm text-green-600">{done}</p>}
      {error && <p className="mt-3 text-sm text-red-500">{error}</p>}
    </div>
  );
}

function pill(active: boolean): string {
  return `rounded-full px-3 py-1 ${
    active ? "bg-zinc-900 text-white dark:bg-white dark:text-zinc-900" : "text-zinc-500"
  }`;
}
