import Link from "next/link";

import { BiggestMoves as BiggestMovesSection } from "@/components/BiggestMoves";
import { BigMoveNote } from "@/components/BigMoveNote";
import { NewsFeed } from "@/components/NewsFeed";
import { OrderForm } from "@/components/OrderForm";
import { PriceChart } from "@/components/PriceChart";
import { Term } from "@/components/Term";
import { TimeMachine } from "@/components/TimeMachine";
import { WatchlistStar } from "@/components/WatchlistStar";
import {
  getBiggestMoves,
  getCandles,
  getNews,
  getPortfolio,
  getStock,
  getWatchlist,
  getWhatIf,
  type BiggestMoves,
  type CandlePoint,
  type NewsItem,
  type Stock,
  type WhatIf,
} from "@/lib/api";
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

  let news: NewsItem[] = [];
  try {
    news = await getNews(upper, token);
  } catch {
    news = []; // news is a nice-to-have; hide the section rather than break the page
  }

  // The moves come off the same cached candles the chart above just used. A failure here
  // hides the section rather than breaking the page.
  let moves: BiggestMoves | null = null;
  try {
    moves = await getBiggestMoves(upper, token);
  } catch {
    moves = null;
  }

  // Render the default what-if with the page so it's there on arrival. It reads the same
  // cached candles the chart above just used, so it costs no provider call.
  let whatIf: WhatIf | null = null;
  try {
    whatIf = await getWhatIf(upper, token);
  } catch {
    whatIf = null; // the component says so and still lets them try another period
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

  // Just the symbols, no quotes: we only need to know whether this one is already watched.
  let watched = false;
  try {
    const items = await getWatchlist(token, false);
    watched = items.some((item) => item.symbol === upper);
  } catch {
    // membership is a nicety; the Watch button still works if we couldn't check
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
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-sm text-zinc-500">{profile?.name ?? quote.symbol}</div>
              <div className="flex items-baseline gap-3">
                <h1 className="text-3xl font-semibold tracking-tight">{quote.symbol}</h1>
                <span className="text-3xl font-semibold tabular-nums">
                  {formatMoney(quote.price)}
                </span>
              </div>
              <div
                className={`mt-1 text-sm tabular-nums ${up ? "text-green-600" : "text-red-600"}`}
              >
                {formatSignedMoney(quote.change)} ({formatPercent(quote.percent_change)}) today
              </div>
            </div>
            <WatchlistStar symbol={quote.symbol} initialWatched={watched} />
          </div>

          {stock.big_move && <BigMoveNote note={stock.big_move} hasNews={news.length > 0} />}

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
                  <Stat
                    label={<Term name="market cap">Market cap</Term>}
                    value={formatCompactMoney(profile.market_cap)}
                  />
                )}
              </div>
            </div>
          )}

          {moves && <BiggestMovesSection moves={moves} />}

          <TimeMachine symbol={quote.symbol} initial={whatIf} />

          <NewsFeed items={news} />
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

function Stat({ label, value }: { label: React.ReactNode; value: string }) {
  return (
    <div>
      <div className="text-zinc-500">{label}</div>
      <div className="mt-0.5 font-medium">{value}</div>
    </div>
  );
}
