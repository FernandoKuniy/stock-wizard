"use server";

import { revalidatePath } from "next/cache";
import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { redeemInvite } from "@/lib/api";
import { INVITE_CODE_KEY, inviteCodeFrom } from "@/lib/invite";
import { createClient } from "@/lib/supabase/server";

export type AuthState = { error?: string; notice?: string };

function credentials(formData: FormData) {
  return {
    email: String(formData.get("email") ?? "").trim(),
    password: String(formData.get("password") ?? ""),
  };
}

/**
 * Where this app is being served from, for the confirmation link to point back at.
 *
 * Read from the request rather than an env var so it's right in every environment without
 * configuration: localhost in development, the real host in production. Whatever it resolves
 * to has to be in the Supabase project's Redirect URLs allow-list, or Supabase refuses it.
 */
async function siteUrl(): Promise<string> {
  const requestHeaders = await headers();
  const host = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host") ?? "";
  const protocol = requestHeaders.get("x-forwarded-proto") ?? "http";
  return `${protocol}://${host}`;
}

/**
 * Redeem the code the user gave at signup, if they have one and haven't used it yet.
 *
 * Idempotent on the API side, so calling it for an account that already exists is a cheap
 * no-op. Failure is deliberately swallowed: they're signed in either way, and /redeem is a
 * better place to sort out a wrong code than an error on the way in.
 */
async function redeemStashedCode(metadata: unknown, token: string): Promise<void> {
  const invite = inviteCodeFrom(metadata);
  if (!invite) return;
  try {
    await redeemInvite(invite, token);
  } catch {
    // Nothing to do here; the redeem screen handles the retry.
  }
}

export async function signIn(_prev: AuthState, formData: FormData): Promise<AuthState> {
  const supabase = await createClient();
  const { data, error } = await supabase.auth.signInWithPassword(credentials(formData));

  if (error) return { error: error.message };

  // Covers the split-device case: confirm the email on a phone, then sign in on the laptop.
  // The code is still in their metadata, so they never have to type it a second time.
  if (data.session) {
    await redeemStashedCode(data.user?.user_metadata, data.session.access_token);
  }

  revalidatePath("/", "layout");
  redirect("/");
}

export async function signUp(_prev: AuthState, formData: FormData): Promise<AuthState> {
  const code = String(formData.get("code") ?? "").trim();
  if (!code) return { error: "You need an invite code to create an account." };

  const supabase = await createClient();
  const { data, error } = await supabase.auth.signUp({
    ...credentials(formData),
    options: {
      // Land the confirmation link on our own route, which turns the token into a session
      // and redeems the code below. Without this it lands on the site root, which has no
      // session yet and bounces to /login.
      emailRedirectTo: `${await siteUrl()}/auth/confirm`,
      // The code has to survive the trip through the user's inbox: there's no session to
      // redeem it with yet, and the form that collected it is gone by the time there is one.
      // Metadata is a carrier, never a credential; the API still verifies it. See lib/invite.
      data: { [INVITE_CODE_KEY]: code },
    },
  });

  if (error) return { error: error.message };

  // With email confirmation on there's no session yet, so the redeem happens at /auth/confirm
  // when they click the link. Nothing more for them to type, so don't ask them to.
  if (!data.session) {
    return {
      notice: "Check your email for a confirmation link. Opening it signs you straight in.",
    };
  }

  // With confirmation off we have a session, so redeem the invite in the same step for a
  // one-shot signup. A wrong code doesn't strand them: they're signed in, so we send them
  // to the redeem screen to try the code again rather than showing a dead end here.
  try {
    await redeemInvite(code, data.session.access_token);
  } catch {
    redirect("/redeem");
  }

  revalidatePath("/", "layout");
  redirect("/");
}

export async function signOut(): Promise<void> {
  const supabase = await createClient();
  await supabase.auth.signOut();

  revalidatePath("/", "layout");
  redirect("/login");
}
