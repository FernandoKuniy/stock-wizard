"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { onAskTutor } from "@/lib/tutor-bus";
import { Tutor } from "./Tutor";

/**
 * The tutor's home: a button in the nav row that opens a slide-over panel.
 *
 * It used to sit at the bottom of the dashboard, which meant it only existed on one page and
 * only after a long scroll. Mounting it in the root layout instead keeps it one click away
 * from everywhere, including a stock page, which is exactly where "what does P/E mean?"
 * actually gets asked. The layout persists across navigation, so the conversation does too.
 */
export function TutorPanel({ messagesLeft = null }: { messagesLeft?: number | null }) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  // A question handed to us by an "explain this" button, keyed so the same finding can be
  // asked again and React's dev double-run doesn't send it twice.
  const [pending, setPending] = useState<{ text: string; key: number } | null>(null);
  const askKey = useRef(0);

  // Closing puts focus back where it came from. Without this a keyboard user lands back at
  // the top of the document and has to tab through the whole header again.
  //
  // It also drops any question that never got asked. One can still be sitting here if it
  // arrived while an earlier answer was streaming, and closing the panel is a clear enough
  // "not now" that reopening it later shouldn't fire it.
  const close = useCallback(() => {
    setOpen(false);
    setPending(null);
    triggerRef.current?.focus();
  }, []);

  // The tutor takes the question the moment it sends it. Clearing it here is what stops it
  // being asked again: the tutor unmounts with the panel, so its own "already asked" guard
  // does not survive a reopen, but this state does.
  const clearPending = useCallback(() => setPending(null), []);

  // An "explain this" button anywhere opens the panel and hands the tutor a question.
  useEffect(
    () =>
      onAskTutor((prompt) => {
        setOpen(true);
        askKey.current += 1;
        setPending({ text: prompt, key: askKey.current });
      }),
    [],
  );

  // Escape closes it, the way anything that covers the page should.
  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") close();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, close]);

  return (
    <>
      <button
        ref={triggerRef}
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
            onClick={close}
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
                onClick={close}
                aria-label="Close the tutor"
                className="rounded-md px-2 py-1 text-lg leading-none text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
              >
                ×
              </button>
            </div>
            <div className="min-h-0 flex-1">
              <Tutor
                pending={pending}
                onPendingHandled={clearPending}
                messagesLeft={messagesLeft}
              />
            </div>
            {/* The glossary lives behind the panel rather than in the nav: it's the same
                "I don't know what that means" moment, and the nav stays at three places. */}
            <div className="shrink-0 border-t border-zinc-200 px-5 py-2.5 dark:border-zinc-800">
              <Link
                href="/glossary"
                onClick={close}
                className="text-xs text-zinc-500 hover:underline"
              >
                Or look a word up in plain English →
              </Link>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
