import Link from "next/link";

// Shown for a URL that doesn't match anything (or a deliberate notFound()). Same calm tone as
// the rest of the app rather than a bare 404.
export default function NotFound() {
  return (
    <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center px-6 py-16 text-center">
      <h1 className="text-2xl font-semibold tracking-tight">Nothing here</h1>
      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
        This page doesn&apos;t exist, or it wandered off. Let&apos;s get you back to your money.
      </p>
      <p className="mt-6 text-sm text-zinc-500">
        <Link href="/" className="underline underline-offset-2">
          Back to your portfolio
        </Link>
      </p>
    </main>
  );
}
