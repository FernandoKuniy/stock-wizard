"use client";

import { useActionState } from "react";

import { redeemCode, type RedeemState } from "./actions";

const EMPTY: RedeemState = {};

export default function RedeemPage() {
  const [state, submit, pending] = useActionState(redeemCode, EMPTY);

  return (
    <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center px-6 py-16">
      <h1 className="text-2xl font-semibold tracking-tight">One more step</h1>
      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
        Stock Wizard is invite-only for now. Enter the code you were given and your $100,000 account
        opens right up.
      </p>

      <form action={submit} className="mt-8 space-y-4">
        <div>
          <label htmlFor="code" className="text-sm text-zinc-500">
            Invite code
          </label>
          <input
            id="code"
            name="code"
            type="text"
            required
            autoFocus
            autoComplete="off"
            className="mt-1 w-full rounded-md border border-zinc-200 bg-transparent px-3 py-2 text-sm outline-none focus:border-zinc-400 dark:border-zinc-800 dark:focus:border-zinc-600"
          />
        </div>

        {state.error && <p className="text-sm text-red-500">{state.error}</p>}

        <button
          type="submit"
          disabled={pending}
          className="w-full rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          {pending ? "One sec…" : "Unlock my account"}
        </button>
      </form>
    </main>
  );
}
