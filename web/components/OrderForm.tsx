"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { placeOrder, type OrderResult } from "@/lib/api";
import { formatMoney, formatShares } from "@/lib/format";
import { getAccessToken } from "@/lib/supabase/client";
import { FirstTimeCallout } from "./FirstTimeCallout";
import { Term } from "./Term";

type Side = "buy" | "sell";
type Mode = "dollars" | "shares";
type OrderType = "market" | "limit";

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
  const [type, setType] = useState<OrderType>("market");
  const [mode, setMode] = useState<Mode>("dollars");
  const [value, setValue] = useState("");
  const [limitValue, setLimitValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const amount = Number(value);
  const limitPrice = Number(limitValue);
  const isLimit = type === "limit";
  const limitOk =
    !isLimit || (limitValue.trim() !== "" && Number.isFinite(limitPrice) && limitPrice > 0);
  const valid = value.trim() !== "" && Number.isFinite(amount) && amount > 0 && limitOk;

  // A limit order is priced at the limit, not at today's quote: that's what it will fill at.
  const fillPrice = isLimit && limitPrice > 0 ? limitPrice : price;
  const estShares = mode === "dollars" ? amount / fillPrice : amount;
  const estCost = mode === "dollars" ? amount : amount * fillPrice;
  const canSell = heldShares > 0;

  async function submit() {
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const result = await placeOrder(
        {
          symbol,
          side,
          mode,
          value: amount,
          type,
          ...(isLimit ? { limit_price: limitPrice } : {}),
        },
        await getAccessToken(),
      );
      setDone(confirmation(side, result));
      setValue("");
      setLimitValue("");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Order failed.");
    } finally {
      setBusy(false);
    }
  }

  const hint = warning({ valid, side, mode, amount, estCost, cash, heldShares, isLimit });

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
          <div className="mt-4 grid grid-cols-2 gap-1 rounded-lg bg-zinc-100 p-1 text-xs dark:bg-zinc-900">
            <button type="button" onClick={() => setType("market")} className={tab(!isLimit)}>
              Buy now
            </button>
            <button type="button" onClick={() => setType("limit")} className={tab(isLimit)}>
              Set a price
            </button>
          </div>

          {isLimit && (
            <label className="mt-3 flex items-center gap-2 rounded-lg border border-zinc-200 px-3 py-2 dark:border-zinc-800">
              <span className="shrink-0 text-xs text-zinc-500">
                {side === "buy" ? "Buy if it drops to" : "Sell if it rises to"}
              </span>
              <span className="text-zinc-500">$</span>
              <input
                type="text"
                inputMode="decimal"
                value={limitValue}
                onChange={(e) => setLimitValue(e.target.value)}
                placeholder={price.toFixed(2)}
                aria-label="Limit price"
                className="w-full bg-transparent tabular-nums outline-none"
              />
            </label>
          )}

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
              {isLimit
                ? limitPlainEnglish({ side, estShares, estCost, symbol, limitPrice })
                : plainEnglish({ side, mode, estShares, estCost, cash, symbol })}
            </p>
          )}

          {hint && <p className="mt-2 text-xs text-amber-600">{hint}</p>}

          <button
            type="button"
            onClick={() => void submit()}
            disabled={busy || !valid}
            className="mt-4 w-full rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-40 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
          >
            {busy
              ? "Placing…"
              : isLimit
                ? `Place limit ${side}`
                : side === "buy"
                  ? `Buy ${symbol}`
                  : `Sell ${symbol}`}
          </button>

          <p className="mt-2 text-center text-xs text-zinc-400">
            {isLimit ? (
              <>
                This is a <Term name="limit order">limit order</Term>. It waits.
              </>
            ) : (
              <>
                This is a <Term name="market order">market order</Term>.
              </>
            )}
          </p>

          {side === "buy" ? (
            <p className="mt-3 text-xs text-zinc-500">You have {formatMoney(cash)} to invest.</p>
          ) : (
            <p className="mt-3 text-xs text-zinc-500">You own {formatShares(heldShares)} shares.</p>
          )}

          <div className="mt-4">
            {isLimit ? (
              <FirstTimeCallout id="limit-order" title="Buying now vs naming your price">
                A market order buys straight away at whatever the price is. A limit order names your
                price and waits, so you never pay more than you meant to. The catch: it might fill
                in a minute, or never. We check your waiting orders when you open your dashboard,
                not every second, so a fill shows up next time you look.
              </FirstTimeCallout>
            ) : (
              <FirstTimeCallout id="first-order" title="What happens when you hit buy">
                It fills straight away at whatever the price is right now. No haggling, no waiting.
                You can put in a dollar amount instead of a number of shares, and you&apos;ll get a
                fraction of a share if that&apos;s what the money buys.
              </FirstTimeCallout>
            )}
          </div>
        </>
      )}

      {done && <p className="mt-3 text-sm text-green-600">{done}</p>}
      {error && <p className="mt-3 text-sm text-red-500">{error}</p>}
    </div>
  );
}

/** Say what the order actually does, in money, not in jargon. */
function plainEnglish(args: {
  side: Side;
  mode: Mode;
  estShares: number;
  estCost: number;
  cash: number;
  symbol: string;
}): string {
  const { side, mode, estShares, estCost, cash, symbol } = args;

  if (side === "buy") {
    const left = cash - estCost;
    const buys =
      mode === "dollars"
        ? `${formatMoney(estCost)} buys about ${formatShares(estShares)} shares of ${symbol}`
        : `About ${formatShares(estShares)} shares costs you around ${formatMoney(estCost)}`;
    if (left < 0) return `${buys}.`;
    return `${buys}, leaving you ${formatMoney(left)} in cash.`;
  }

  return `You'd get about ${formatMoney(estCost)} back, bringing your cash to ${formatMoney(
    cash + estCost,
  )}.`;
}

/** The same idea for an order that hasn't happened yet: what it does if the price arrives. */
function limitPlainEnglish(args: {
  side: Side;
  estShares: number;
  estCost: number;
  symbol: string;
  limitPrice: number;
}): string {
  const { side, estShares, estCost, symbol, limitPrice } = args;
  const move = side === "buy" ? "drops to" : "rises to";
  const does =
    side === "buy"
      ? `this buys about ${formatShares(estShares)} shares for ${formatMoney(estCost)}`
      : `this sells ${formatShares(estShares)} shares for about ${formatMoney(estCost)}`;
  return `If ${symbol} ${move} ${formatMoney(limitPrice)}, ${does}.`;
}

function confirmation(side: Side, result: OrderResult): string {
  if (result.order) {
    const { quantity, symbol, limit_price } = result.order;
    const verb = side === "buy" ? "Buying" : "Selling";
    return `Order placed. ${verb} ${formatShares(quantity)} ${symbol} if it hits ${formatMoney(
      limit_price,
    )}.`;
  }
  const txn = result.transaction;
  if (!txn) return "Order placed.";
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
  isLimit: boolean;
}): string | null {
  const { valid, side, mode, amount, estCost, cash, heldShares, isLimit } = args;
  if (!valid) return null;
  if (side === "buy" && estCost > cash) {
    // Nothing is set aside for a waiting order, so this isn't a blocker, just a heads-up.
    return isLimit
      ? `That would cost about ${formatMoney(estCost)}. You have ${formatMoney(
          cash,
        )}, so unless you free up cash, this one won't fill.`
      : `That's about ${formatMoney(estCost)}, more than your ${formatMoney(cash)} in cash.`;
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
