"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { redeemInvite } from "@/lib/api";
import { getAccessToken } from "@/lib/supabase/server";

export type RedeemState = { error?: string };

export async function redeemCode(_prev: RedeemState, formData: FormData): Promise<RedeemState> {
  const code = String(formData.get("code") ?? "").trim();
  if (!code) return { error: "Enter your invite code." };

  const token = await getAccessToken();
  // Redeeming needs a signed-in session. If it's gone, sign in again first.
  if (!token) redirect("/login");

  try {
    await redeemInvite(code, token);
  } catch (e) {
    // A wrong code comes back as an error; let them try again rather than stranding them.
    return { error: e instanceof Error ? e.message : "That didn't work. Try again." };
  }

  // The account exists now, so the app's pages have something to show.
  revalidatePath("/", "layout");
  redirect("/");
}
