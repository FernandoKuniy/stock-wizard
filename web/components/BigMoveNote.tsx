/**
 * A pointer to today's headlines when a stock has had an unusual day.
 *
 * The product spec has always asked for "a one-line 'why did this move?' on big price
 * changes, pulled from news". This is the honest version of that: the backend decides the day
 * is unusual and writes the sentence, and the copy points at the headlines without ever
 * claiming they are the reason. Plenty of big days have no explanation you can point at, and
 * teaching a beginner to always find one teaches them to see patterns that aren't there.
 *
 * Amber, not red or green. A big move in either direction is worth a look, and neither is a
 * gain or a loss until you own the thing.
 */
export function BigMoveNote({ note, hasNews }: { note: string; hasNews: boolean }) {
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50/60 px-4 py-3 dark:border-amber-900 dark:bg-amber-950/30">
      <p className="text-sm text-amber-900 dark:text-amber-200">{note}</p>
      <p className="mt-1 text-xs text-amber-800/80 dark:text-amber-300/80">
        {hasNews ? (
          <>
            <a href="#news" className="underline underline-offset-2">
              Here&apos;s what&apos;s been in the news
            </a>
            . Headlines don&apos;t always explain a move, and plenty of big days have no reason you
            can point at.
          </>
        ) : (
          <>
            There&apos;s no recent news here to check. Plenty of big days have no reason you can
            point at anyway.
          </>
        )}
      </p>
    </div>
  );
}
