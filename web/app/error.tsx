"use client";

// Catches an unhandled error anywhere in the app and shows a calm way out, so a prod hiccup
// never drops someone onto a stack trace. Client component by requirement (it holds `reset`).

import Link from "next/link";
import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // No error tracker wired up (deliberately, for a demo), so at least log it for the console.
    console.error(error);
  }, [error]);

  return (
    <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center px-6 py-16 text-center">
      <h1 className="text-2xl font-semibold tracking-tight">That didn&apos;t load right</h1>
      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
        Something on our end glitched, not anything you did, and none of your (pretend) money is
        affected. Give it another go.
      </p>
      <button
        onClick={reset}
        className="mt-6 rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
      >
        Try again
      </button>
      <p className="mt-6 text-sm text-zinc-500">
        <Link href="/" className="underline underline-offset-2">
          Back to your portfolio
        </Link>
      </p>
    </main>
  );
}
