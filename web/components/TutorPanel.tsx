"use client";

import { useEffect, useState } from "react";

import { Tutor } from "./Tutor";

/**
 * The tutor's home: a button in the nav row that opens a slide-over panel.
 *
 * It used to sit at the bottom of the dashboard, which meant it only existed on one page and
 * only after a long scroll. Mounting it in the root layout instead keeps it one click away
 * from everywhere, including a stock page, which is exactly where "what does P/E mean?"
 * actually gets asked. The layout persists across navigation, so the conversation does too.
 */
export function TutorPanel() {
  const [open, setOpen] = useState(false);

  // Escape closes it, the way anything that covers the page should.
  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Ask the tutor"
        aria-expanded={open}
        className="my-1.5 shrink-0 rounded-full border border-indigo-200 bg-indigo-50/60 px-3 py-1 text-sm text-indigo-700 hover:bg-indigo-100 dark:border-indigo-900 dark:bg-indigo-950/40 dark:text-indigo-300 dark:hover:bg-indigo-950"
      >
        <span className="hidden sm:inline">Ask the tutor</span>
        <span className="sm:hidden">Ask</span>
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex justify-end">
          {/* Clicking away closes it. It's a panel, not a decision, so it shouldn't trap you. */}
          <button
            type="button"
            aria-label="Close the tutor"
            onClick={() => setOpen(false)}
            className="absolute inset-0 bg-zinc-900/20 backdrop-blur-[1px] dark:bg-zinc-950/50"
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Ask the tutor"
            className="relative flex h-full w-full max-w-md flex-col border-l border-zinc-200 bg-white shadow-xl dark:border-zinc-800 dark:bg-zinc-950"
          >
            <div className="flex shrink-0 items-center justify-between gap-4 border-b border-zinc-200 px-5 py-3 dark:border-zinc-800">
              <h2 className="text-sm font-semibold">Ask the tutor</h2>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close the tutor"
                className="rounded-md px-2 py-1 text-lg leading-none text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
              >
                ×
              </button>
            </div>
            <div className="min-h-0 flex-1">
              <Tutor />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
