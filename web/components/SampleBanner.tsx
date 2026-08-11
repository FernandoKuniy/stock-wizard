/**
 * Shown while an account still holds the demo sample we seed new accounts with, so a
 * first-time visitor lands on a dashboard that teaches (a real curve, a check-up, a what-if)
 * instead of a blank screen. It says plainly that these aren't their picks, and points at
 * reset as the way to start their own. A reset clears the flag and this goes away.
 *
 * Info-blue on purpose: amber is for "notable" and red/green are for money, so neither fits a
 * plain heads-up.
 */
export function SampleBanner() {
  return (
    <div className="rounded-lg border border-sky-200 bg-sky-50/60 px-4 py-3 text-sm text-sky-900 dark:border-sky-900 dark:bg-sky-950/30 dark:text-sky-200">
      <p className="font-medium">
        This is a sample portfolio, so there&apos;s something to look at.
      </p>
      <p className="mt-1 text-sky-800 dark:text-sky-300">
        We bought a few well-known companies at real prices a while back, so the chart and the rest
        of the page have a story to tell. None of it is your pick. When you want to start your own,
        hit reset at the bottom and you&apos;ll get a clean $100,000 to run yourself.
      </p>
    </div>
  );
}
