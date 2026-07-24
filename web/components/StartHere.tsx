"use client";

import { formatMoney } from "@/lib/format";
import { SEARCH_INPUT_ID } from "./TickerSearch";

/**
 * What to do first, for an account that owns nothing yet.
 *
 * The emptiest screen is where a beginner is most likely to give up, and "you've got $100,000
 * to invest" on its own is a prompt without a path. These are three steps about **how the app
 * works**, never about what to buy.
 *
 * That distinction is hard rule #2 and it is the whole reason this is worded so carefully. It
 * never names a company, a ticker, or a kind of fund. "Start with a company you already know"
 * is a way to make the search box less intimidating, not a recommendation; the app has no
 * opinion on what belongs in your portfolio, and saying otherwise would make it an adviser.
 *
 * Step three is the one that matters most and the one a trading app would never write.
 */
export function StartHere({ cash }: { cash: number }) {
  function focusSearch() {
    const input = document.getElementById(SEARCH_INPUT_ID);
    if (input instanceof HTMLInputElement) {
      input.scrollIntoView({ block: "center" });
      input.focus();
    }
  }

  return (
    <section className="rounded-xl border border-dashed border-zinc-300 p-6 dark:border-zinc-700">
      <h2 className="text-lg font-medium">
        You&apos;ve got <span className="calm">{formatMoney(cash)}</span> of fake money. Here&apos;s
        where to start.
      </h2>

      <ol className="mt-4 space-y-4">
        <Step number={1} title="Look up a company you already know">
          Anything you&apos;ve heard of works. You&apos;ll get its price, a plain-English line on
          what it actually does, and how it&apos;s moved.{" "}
          <button
            type="button"
            onClick={focusSearch}
            className="underline underline-offset-2 hover:text-zinc-900 dark:hover:text-zinc-100"
          >
            Put the cursor in the search box
          </button>
          .
        </Step>

        <Step number={2} title="Buy a small piece of it">
          You can spend a dollar amount instead of counting shares, so nothing has to be a round
          number. It&apos;s not real money, and there&apos;s a reset button when you want a clean
          slate.
        </Step>

        <Step number={3} title="Then leave it alone for a bit">
          The chart on this page starts meaning something after weeks, not hours. Checking daily is
          the habit that costs beginners the most, and it&apos;s the one this app is built to talk
          you out of.
        </Step>
      </ol>
    </section>
  );
}

function Step({
  number,
  title,
  children,
}: {
  number: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <li className="flex gap-3">
      <span
        aria-hidden
        className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-zinc-100 text-xs font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300"
      >
        {number}
      </span>
      <div className="min-w-0">
        <div className="text-sm font-medium">{title}</div>
        <p className="mt-0.5 text-sm text-zinc-600 dark:text-zinc-400">{children}</p>
      </div>
    </li>
  );
}
