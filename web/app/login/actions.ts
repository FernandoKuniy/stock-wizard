"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { redeemInvite } from "@/lib/api";
import { createClient } from "@/lib/supabase/server";

export type AuthState = { error?: string; notice?: string };

function credentials(formData: FormData) {
  return {
    email: String(formData.get("email") ?? "").trim(),
    password: String(formData.get("password") ?? ""),
  };
}

export async function signIn(_prev: AuthState, formData: FormData): Promise<AuthState> {
  const supabase = await createClient();
  const { error } = await supabase.auth.signInWithPassword(credentials(formData));

  if (error) return { error: error.message };

  revalidatePath("/", "layout");
  redirect("/");
}

export async function signUp(_prev: AuthState, formData: FormData): Promise<AuthState> {
  const code = String(formData.get("code") ?? "").trim();
  if (!code) return { error: "You need an invite code to create an account." };

  const supabase = await createClient();
  const { data, error } = await supabase.auth.signUp(credentials(formData));

  if (error) return { error: error.message };

  // With email confirmation turned on there's no session yet, so we can't redeem the code
  // now. Tell them to confirm and sign in; the redeem screen will ask for the code then.
  if (!data.session) {
    return { notice: "Check your email for a confirmation link, then come back and sign in." };
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
