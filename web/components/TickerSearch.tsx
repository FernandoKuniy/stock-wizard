"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useRef, useState } from "react";

import { searchSymbols, type SymbolMatch } from "@/lib/api";
import { getAccessToken } from "@/lib/supabase/client";

export function TickerSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SymbolMatch[]>([]);
  const [open, setOpen] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  function onChange(next: string) {
    setQuery(next);
    setOpen(true);
    if (timer.current) clearTimeout(timer.current);
    if (next.trim().length < 1) {
      setResults([]);
      return;
    }
    // Debounce so we only search once the user pauses, staying under the free tier.
    timer.current = setTimeout(() => {
      getAccessToken()
        .then((token) => searchSymbols(next, token))
        .then(setResults)
        .catch(() => setResults([]));
    }, 200);
  }

  function go(symbol: string) {
    setQuery("");
    setResults([]);
    setOpen(false);
    router.push(`/stock/${encodeURIComponent(symbol)}`);
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const first = results[0];
    if (first) go(first.symbol);
    else if (query.trim()) go(query.trim().toUpperCase());
  }

  return (
    <form onSubmit={onSubmit} className="relative">
      <input
        type="text"
        value={query}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder="Search a ticker or company…"
        aria-label="Search stocks"
        className="w-full rounded-md border border-zinc-200 bg-transparent px-3 py-1.5 text-sm outline-none focus:border-zinc-400 dark:border-zinc-800 dark:focus:border-zinc-600"
      />
      {open && results.length > 0 && (
        <ul className="absolute z-10 mt-1 max-h-72 w-full overflow-auto rounded-md border border-zinc-200 bg-white py-1 shadow-lg dark:border-zinc-800 dark:bg-zinc-950">
          {results.map((match) => (
            <li key={match.symbol}>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => go(match.symbol)}
                className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-zinc-100 dark:hover:bg-zinc-900"
              >
                <span className="font-medium">{match.symbol}</span>
                <span className="truncate text-zinc-500">{match.description}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </form>
  );
}
