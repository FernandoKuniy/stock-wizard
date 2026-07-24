"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * Calm mode: blur the money figures.
 *
 * The one thing a nervous beginner reliably does wrong is react to a red number, and the
 * product is explicitly built for a nervous beginner. So this is the rare feature that is
 * deliberately anti-engagement: it lets someone open the app, see that they're up or down,
 * and stop, without a figure to chew on. Hovering any blurred figure reveals it, so checking
 * on purpose is still one gesture away.
 *
 * The state is an attribute on <html>, not React state, so the server components that render
 * the figures stay server components. Like the first-time explainers, "on" lives in
 * localStorage: it's a UI preference, not money, and doesn't justify a table or a round trip.
 */
const KEY = "stockwizard.calm";

// localStorage and the DOM attribute are both external stores, so React reads them through
// useSyncExternalStore rather than copying into state inside an effect.
const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function CalmToggle() {
  const calm = useSyncExternalStore(
    subscribe,
    () => document.documentElement.dataset.calm === "on",
    // On the server there is no DOM. Assume off, which matches what the pre-paint script in
    // the layout renders when nothing is stored.
    () => false,
  );

  const toggle = useCallback(() => {
    const next = document.documentElement.dataset.calm !== "on";
    if (next) {
      document.documentElement.dataset.calm = "on";
      window.localStorage.setItem(KEY, "on");
    } else {
      delete document.documentElement.dataset.calm;
      window.localStorage.removeItem(KEY);
    }
    listeners.forEach((listener) => listener());
  }, []);

  return (
    <button
      type="button"
      onClick={toggle}
      aria-pressed={calm}
      title={calm ? "Show the amounts again" : "Blur the amounts so you can look without reacting"}
      className="my-1.5 shrink-0 rounded-full border border-zinc-200 px-3 py-1 text-sm text-zinc-500 hover:bg-zinc-50 hover:text-zinc-800 dark:border-zinc-800 dark:hover:bg-zinc-900 dark:hover:text-zinc-200"
    >
      {calm ? "Show amounts" : "Hide amounts"}
    </button>
  );
}
