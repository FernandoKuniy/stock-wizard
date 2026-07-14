"use client";

import { useActionState } from "react";

import { signIn, signUp, type AuthState } from "./actions";

const EMPTY: AuthState = {};

export default function LoginPage() {
  const [state, submit, pending] = useActionState(
    async (prev: AuthState, formData: FormData) =>
      formData.get("intent") === "signup" ? signUp(prev, formData) : signIn(prev, formData),
    EMPTY,
  );

  return (
    <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center px-6 py-16">
      <h1 className="text-2xl font-semibold tracking-tight">Start investing, risk free</h1>
      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
        You get $100,000 of fake money and real market prices. Nothing here costs you a cent.
      </p>

      <form className="mt-8 space-y-4">
        <div>
          <label htmlFor="email" className="text-sm text-zinc-500">
            Email
          </label>
          <input
            id="email"
            name="email"
            type="email"
            required
            autoComplete="email"
            className="mt-1 w-full rounded-md border border-zinc-200 bg-transparent px-3 py-2 text-sm outline-none focus:border-zinc-400 dark:border-zinc-800 dark:focus:border-zinc-600"
          />
        </div>

        <div>
          <label htmlFor="password" className="text-sm text-zinc-500">
            Password
          </label>
          <input
            id="password"
            name="password"
            type="password"
            required
            minLength={6}
            autoComplete="current-password"
            className="mt-1 w-full rounded-md border border-zinc-200 bg-transparent px-3 py-2 text-sm outline-none focus:border-zinc-400 dark:border-zinc-800 dark:focus:border-zinc-600"
          />
        </div>

        {state.error && <p className="text-sm text-red-500">{state.error}</p>}
        {state.notice && <p className="text-sm text-zinc-600 dark:text-zinc-400">{state.notice}</p>}

        <div className="flex gap-2 pt-2">
          <button
            type="submit"
            name="intent"
            value="signin"
            formAction={submit}
            disabled={pending}
            className="flex-1 rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
          >
            {pending ? "One sec…" : "Sign in"}
          </button>
          <button
            type="submit"
            name="intent"
            value="signup"
            formAction={submit}
            disabled={pending}
            className="flex-1 rounded-md border border-zinc-200 px-3 py-2 text-sm font-medium hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-800 dark:hover:bg-zinc-900"
          >
            Create account
          </button>
        </div>
      </form>

      <p className="mt-10 text-center text-xs text-zinc-500">
        Simulation for education. Not financial advice.
      </p>
    </main>
  );
}
