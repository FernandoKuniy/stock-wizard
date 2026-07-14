import Link from "next/link";

import { OrderForm } from "@/components/OrderForm";
import { PriceChart } from "@/components/PriceChart";
import { getCandles, getPortfolio, getStock, type CandlePoint, type Stock } from "@/lib/api";
import { formatCompactMoney, formatMoney, formatPercent, formatSignedMoney } from "@/lib/format";
import { getAccessToken } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export default async function StockPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  const upper = decodeURIComponent(symbol).toUpperCase();
  const token = await getAccessToken();

  let stock: Stock;
  try {
    stock = await getStock(upper, token);
  } catch (e) {
    return (
      <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-10">
        <Link href="/" className="text-sm text-zinc-500 hover:underline">
          ← Back to portfolio
        </Link>
        <p className="mt-6 text-sm text-red-500">
          {e instanceof Error ? e.message : `Couldn't load ${upper}.`}
        </p>
      </main>
    );
  }

  let candles: CandlePoint[] | null = null;
  try {
    candles = (await getCandles(upper, token)).points;
  } catch {
    candles = null; // chart unavailable (e.g. no Twelve Data key); the page still works
  }

  let cash = 0;
  let heldShares = 0;
  try {
    const portfolio = await getPortfolio(token);
    cash = portfolio.cash;
    heldShares = portfolio.holdings.find((h) => h.symbol === upper)?.quantity ?? 0;
  } catch {
    // leave defaults; the order form still works and the backend is authoritative
  }

  const { quote, profile } = stock;
  const up = quote.change >= 0;

  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-10">
      <Link href="/" className="text-sm text-zinc-500 hover:underline">
        ← Back to portfolio
      </Link>

      <div className="mt-6 grid gap-8 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <div>
            <div className="text-sm text-zinc-500">{profile?.name ?? quote.symbol}</div>
            <div className="flex items-baseline gap-3">
              <h1 className="text-3xl font-semibold tracking-tight">{quote.symbol}</h1>
              <span className="text-3xl font-semibold tabular-nums">
                {formatMoney(quote.price)}
              </span>
            </div>
            <div className={`mt-1 text-sm tabular-nums ${up ? "text-green-600" : "text-red-600"}`}>
              {formatSignedMoney(quote.change)} ({formatPercent(quote.percent_change)}) today
            </div>
          </div>

          {candles ? (
            <PriceChart points={candles} />
          ) : (
            <p className="text-sm text-zinc-500">Price history isn&apos;t available right now.</p>
          )}

          {profile && (
            <div className="rounded-xl border border-zinc-200 p-5 dark:border-zinc-800">
              <p className="text-sm text-zinc-700 dark:text-zinc-300">{profile.blurb}</p>
              <div className="mt-4 grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
                {profile.industry && <Stat label="Industry" value={profile.industry} />}
                {profile.exchange && <Stat label="Exchange" value={profile.exchange} />}
                {profile.market_cap > 0 && (
                  <Stat label="Market cap" value={formatCompactMoney(profile.market_cap)} />
                )}
              </div>
            </div>
          )}
        </div>

        <div className="lg:col-span-1">
          <OrderForm
            symbol={quote.symbol}
            price={quote.price}
            cash={cash}
            heldShares={heldShares}
          />
        </div>
      </div>

      <p className="mt-10 text-center text-xs text-zinc-500">
        Simulation for education. Not financial advice.
      </p>
    </main>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-zinc-500">{label}</div>
      <div className="mt-0.5 font-medium">{value}</div>
    </div>
  );
}
