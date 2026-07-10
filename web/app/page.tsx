import { LiveQuote } from "@/components/LiveQuote";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center gap-6 px-6 text-center">
      <h1 className="text-4xl font-semibold tracking-tight">Stock Wizard</h1>
      <p className="text-lg text-zinc-600 dark:text-zinc-400">
        Learn investing with fake money and real market prices.
      </p>
      <LiveQuote symbol="AAPL" />
      <p className="text-sm text-zinc-500">Simulation for education. Not financial advice.</p>
    </main>
  );
}
