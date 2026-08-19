"use client";

import { useState } from "react";

// Where someone goes to ask for a code without a cap. Not an env var: it's the author's own
// site, and a demo that can't say who to ask is a dead end.
const PORTFOLIO_URL = "https://fernando-kuniy.vercel.app/";

/**
 * What replaces the tutor's composer once a demo account has used its questions.
 *
 * Two jobs: say plainly that the tutor is done and point at a way to get more, and take the
 * code if they've already been sent one. The redeem call is passed in rather than made here,
 * so this stays a presentational component that renders from props and tests without a
 * network. It returns an error message, or null once the upgrade went through.
 */
export function DemoLimitBanner({
  onUpgrade,
}: {
  onUpgrade: (code: string) => Promise<string | null>;
}) {
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const entered = code.trim();
    if (entered === "" || busy) return;
    setBusy(true);
    setError(null);
    try {
      setError(await onUpgrade(entered));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="shrink-0 space-y-3 border-t border-zinc-200 px-5 py-4 dark:border-zinc-800">
      <div className="space-y-1">
        <p className="text-sm font-medium">That was your free question</p>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          The demo code comes with one, because every answer costs real money to generate. The rest
          of the app stays open: keep buying, selling, and poking at the charts.
        </p>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Want the tutor without the cap?{" "}
          <a
            href={PORTFOLIO_URL}
            target="_blank"
            rel="noreferrer"
            className="text-indigo-600 underline underline-offset-2 dark:text-indigo-400"
          >
            Ask me for a code
          </a>{" "}
          and I&apos;ll send one over.
        </p>
      </div>

      <form onSubmit={submit} className="flex items-center gap-2">
        <input
          type="text"
          value={code}
          onChange={(event) => setCode(event.target.value)}
          placeholder="Already have one?"
          aria-label="Enter a code to unlock the tutor"
          autoComplete="off"
          className="w-full rounded-md border border-zinc-200 bg-transparent px-3 py-1.5 text-sm outline-none focus:border-zinc-400 dark:border-zinc-800 dark:focus:border-zinc-600"
        />
        <button
          type="submit"
          disabled={busy || code.trim() === ""}
          className="shrink-0 rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-40 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          {busy ? "One sec…" : "Unlock"}
        </button>
      </form>

      {error && <p className="text-sm text-red-500">{error}</p>}
    </div>
  );
}
