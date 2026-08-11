// The route-level loading state, shown while a server component fetches. Deliberately quiet:
// a nervous beginner doesn't need a spinner racing on a screen about their money.
export default function Loading() {
  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 items-center px-6 py-10">
      <p className="text-sm text-zinc-500">Loading…</p>
    </main>
  );
}
