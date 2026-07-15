"use client";

import { useState } from "react";

import { addToWatchlist, removeFromWatchlist } from "@/lib/api";
import { getAccessToken } from "@/lib/supabase/client";

/**
 * The Watch button on a stock page: the one place you add a stock to your watchlist, and a
 * quick way to drop it again. Adding costs nothing and buys nothing; it just tracks the
 * ticker. The toggle is optimistic and reverts if the request fails.
 */
export function WatchlistStar({
  symbol,
  initialWatched,
}: {
  symbol: string;
  initialWatched: boolean;
}) {
  const [watched, setWatched] = useState(initialWatched);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    const next = !watched;
    setBusy(true);
    setError(null);
    setWatched(next); // optimistic; the backend is authoritative if this fails
    try {
      const token = await getAccessToken();
      if (next) await addToWatchlist(symbol, token);
      else await removeFromWatchlist(symbol, token);
    } catch (e) {
      setWatched(!next);
      setError(e instanceof Error ? e.message : "Couldn't update your watchlist.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={() => void toggle()}
        disabled={busy}
        aria-pressed={watched}
        className={`flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium disabled:opacity-50 ${
          watched
            ? "border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300"
            : "border-zinc-200 text-zinc-600 hover:bg-zinc-50 dark:border-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-900"
        }`}
      >
        <span aria-hidden>{watched ? "★" : "☆"}</span>
        {watched ? "Watching" : "Watch"}
      </button>
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  );
}
