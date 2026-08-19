"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useActionState } from "react";

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

      <form action={submit} className="mt-8 space-y-4">
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

        <div>
          <label htmlFor="code" className="text-sm text-zinc-500">
            Invite code
          </label>
          <input
            id="code"
            name="code"
            type="text"
            autoComplete="off"
            className="mt-1 w-full rounded-md border border-zinc-200 bg-transparent px-3 py-2 text-sm outline-none focus:border-zinc-400 dark:border-zinc-800 dark:focus:border-zinc-600"
          />
          <p className="mt-1 text-xs text-zinc-400">Only needed to create an account.</p>
        </div>

        <Suspense fallback={null}>
          <ConfirmationNotice />
        </Suspense>
        {state.error && <p className="text-sm text-red-500">{state.error}</p>}
        {state.notice && <p className="text-sm text-zinc-600 dark:text-zinc-400">{state.notice}</p>}

        <div className="flex gap-2 pt-2">
          <button
            type="submit"
            name="intent"
            value="signin"
            disabled={pending}
            className="flex-1 rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
          >
            {pending ? "One sec…" : "Sign in"}
          </button>
          <button
            type="submit"
            name="intent"
            value="signup"
            disabled={pending}
            className="flex-1 rounded-md border border-zinc-200 px-3 py-2 text-sm font-medium hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-800 dark:hover:bg-zinc-900"
          >
            Create account
          </button>
        </div>
      </form>
    </main>
  );
}

/**
 * Shown when a confirmation link didn't work: expired, already used, or opened in a different
 * browser than it was requested from (the PKCE case). Signing in normally works from here, so
 * this says that rather than dwelling on why. Kept vague on purpose: a login screen shouldn't
 * confirm whether an address has an account.
 */
function ConfirmationNotice() {
  const confirmed = useSearchParams().get("confirmed");
  if (confirmed !== "0") return null;
  return (
    <p className="text-sm text-zinc-600 dark:text-zinc-400">
      That confirmation link has already been used or has expired. Sign in below and you&apos;re in.
    </p>
  );
}
