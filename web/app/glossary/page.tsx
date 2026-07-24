import Link from "next/link";

import { GLOSSARY, slugForTerm } from "@/lib/glossary";

export const metadata = {
  title: "Plain English · Stock Wizard",
  description: "Every bit of jargon in the app, explained without more jargon.",
};

/**
 * The whole glossary on one page.
 *
 * These definitions already existed behind every <Term> tooltip, and on the tutor's side of
 * the wire, with no way to just browse them. This is not the "Learn tab nobody visits" the
 * product spec warns against: it holds no lessons and no course, only the same words the app
 * already uses, in one place, so someone can look one up without hunting for the screen that
 * happens to mention it. Each term has an anchor, so anything can link straight to one.
 */
export default function GlossaryPage() {
  // Alphabetical, ignoring case, because this is a reference and not a curriculum.
  const terms = Object.entries(GLOSSARY).sort(([a], [b]) =>
    a.toLowerCase().localeCompare(b.toLowerCase()),
  );

  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Plain English</h1>
      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
        Every bit of jargon the app puts on screen, explained without more jargon. You&apos;ll also
        see these as dotted underlines wherever the word comes up, so you rarely have to come here
        on purpose.
      </p>

      <dl className="mt-8 space-y-6">
        {terms.map(([term, definition]) => (
          <div key={term} id={slugForTerm(term)} className="scroll-mt-24">
            <dt className="text-sm font-medium">{term}</dt>
            <dd className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{definition}</dd>
          </div>
        ))}
      </dl>

      <p className="mt-10 text-sm text-zinc-500">
        Still stuck on something?{" "}
        <Link href="/" className="underline underline-offset-2">
          Ask the tutor
        </Link>{" "}
        about your own portfolio, in your own words.
      </p>

      <p className="mt-10 text-center text-xs text-zinc-500">
        Simulation for education. Not financial advice.
      </p>
    </main>
  );
}
