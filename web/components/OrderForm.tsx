"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { placeOrder, type OrderResult } from "@/lib/api";
import { formatMoney, formatShares } from "@/lib/format";

type Side = "buy" | "sell";
type Mode = "dollars" | "shares";

export function OrderForm({
  symbol,
  price,
  cash,
  heldShares,
}: {
  symbol: string;
  price: number;
  cash: number;
  heldShares: number;
}) {
  const router = useRouter();
  const [side, setSide] = useState<Side>("buy");
  const [mode, setMode] = useState<Mode>("dollars");
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const amount = Number(value);
  const valid = value.trim() !== "" && Number.isFinite(amount) && amount > 0;
  const estShares = mode === "dollars" ? amount / price : amount;
  const estCost = mode === "dollars" ? amount : amount * price;
  const canSell = heldShares > 0;

  async function submit() {
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const result = await placeOrder({ symbol, side, mode, value: amount });
      setDone(confirmation(side, result));
      setValue("");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Order failed.");
    } finally {
      setBusy(false);
    }
  }

  const hint = warning({ valid, side, mode, amount, estCost, cash, heldShares });

  return (
    <div className="rounded-xl border border-zinc-200 p-5 dark:border-zinc-800">
      <div className="grid grid-cols-2 gap-1 rounded-lg bg-zinc-100 p-1 text-sm dark:bg-zinc-900">
        <button type="button" onClick={() => setSide("buy")} className={tab(side === "buy")}>
          Buy
        </button>
        <button
          type="button"
          onClick={() => setSide("sell")}
          disabled={!canSell}
          className={`${tab(side === "sell")} disabled:cursor-not-allowed disabled:opacity-40`}
        >
          Sell
        </button>
      </div>

      {side === "sell" && !canSell ? (
        <p className="mt-4 text-sm text-zinc-500">You don&apos;t own any {symbol} to sell yet.</p>
      ) : (
        <>
          <div className="mt-4 flex gap-2 text-xs">
            <button
              type="button"
              onClick={() => setMode("dollars")}
              className={pill(mode === "dollars")}
            >
              Dollars
            </button>
            <button
              type="button"
              onClick={() => setMode("shares")}
              className={pill(mode === "shares")}
            >
              Shares
            </button>
          </div>

          <label className="mt-3 flex items-center gap-2 rounded-lg border border-zinc-200 px-3 py-2 dark:border-zinc-800">
            {mode === "dollars" && <span className="text-zinc-500">$</span>}
            <input
              type="text"
              inputMode="decimal"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={mode === "dollars" ? "0.00" : "0"}
              aria-label={mode === "dollars" ? "Dollar amount" : "Number of shares"}
              className="w-full bg-transparent tabular-nums outline-none"
            />
            {mode === "shares" && <span className="text-zinc-500">shares</span>}
          </label>

          {valid && (
            <p className="mt-2 text-xs text-zinc-500">
              {mode === "dollars"
                ? `About ${formatShares(estShares)} shares`
                : `About ${formatMoney(estCost)}`}{" "}
              at the current price.
            </p>
          )}

          {hint && <p className="mt-2 text-xs text-amber-600">{hint}</p>}

          <button
            type="button"
            onClick={() => void submit()}
            disabled={busy || !valid}
            className="mt-4 w-full rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-40 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
          >
            {busy ? "Placing…" : side === "buy" ? `Buy ${symbol}` : `Sell ${symbol}`}
          </button>

          <p className="mt-2 text-center text-xs text-zinc-400">Fills at the current price.</p>

          {side === "buy" ? (
            <p className="mt-3 text-xs text-zinc-500">You have {formatMoney(cash)} to invest.</p>
          ) : (
            <p className="mt-3 text-xs text-zinc-500">You own {formatShares(heldShares)} shares.</p>
          )}
        </>
      )}

      {done && <p className="mt-3 text-sm text-green-600">{done}</p>}
      {error && <p className="mt-3 text-sm text-red-500">{error}</p>}
    </div>
  );
}

function confirmation(side: Side, result: OrderResult): string {
  const txn = result.transaction;
  const verb = side === "buy" ? "Bought" : "Sold";
  return `${verb} ${formatShares(txn.quantity)} ${txn.symbol} for ${formatMoney(txn.total)}.`;
}

function warning(args: {
  valid: boolean;
  side: Side;
  mode: Mode;
  amount: number;
  estCost: number;
  cash: number;
  heldShares: number;
}): string | null {
  const { valid, side, mode, amount, estCost, cash, heldShares } = args;
  if (!valid) return null;
  if (side === "buy" && estCost > cash) {
    return `That's about ${formatMoney(estCost)}, more than your ${formatMoney(cash)} in cash.`;
  }
  if (side === "sell" && mode === "shares" && amount > heldShares) {
    return `You only own ${formatShares(heldShares)} shares.`;
  }
  return null;
}

function tab(active: boolean): string {
  return `rounded-md px-3 py-1.5 font-medium ${
    active ? "bg-white shadow-sm dark:bg-zinc-700" : "text-zinc-500"
  }`;
}

function pill(active: boolean): string {
  return `rounded-full px-3 py-1 ${
    active ? "bg-zinc-900 text-white dark:bg-white dark:text-zinc-900" : "text-zinc-500"
  }`;
}
