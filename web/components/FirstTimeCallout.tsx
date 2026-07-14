"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * A short explainer that shows up the first time someone meets a new idea, then gets out
 * of the way forever.
 *
 * "Seen" lives in localStorage rather than the database. It's a UI preference, not
 * something anyone's money depends on, and it isn't worth a table or a round trip.
 */

// localStorage is an external store, so React reads it through useSyncExternalStore rather
// than by copying it into state inside an effect. Dismissing notifies every callout at once.
const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function FirstTimeCallout({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  const key = `stockwizard.seen.${id}`;

  const seen = useSyncExternalStore(
    subscribe,
    () => window.localStorage.getItem(key) !== null,
    // On the server there's no localStorage. Assume it's been seen, so a returning user
    // never gets a flash of a callout they dismissed months ago.
    () => true,
  );

  const dismiss = useCallback(() => {
    window.localStorage.setItem(key, "seen");
    listeners.forEach((listener) => listener());
  }, [key]);

  if (seen) return null;

  return (
    <aside className="rounded-xl border border-indigo-200 bg-indigo-50/60 p-4 dark:border-indigo-900 dark:bg-indigo-950/30">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-medium text-indigo-900 dark:text-indigo-200">{title}</h2>
          <div className="mt-1 text-sm text-indigo-800/90 dark:text-indigo-300/90">{children}</div>
        </div>
        <button
          type="button"
          onClick={dismiss}
          className="shrink-0 text-xs text-indigo-700/70 hover:text-indigo-900 dark:text-indigo-400/70 dark:hover:text-indigo-200"
        >
          Got it
        </button>
      </div>
    </aside>
  );
}
