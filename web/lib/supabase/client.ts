// The Supabase client for code running in the browser.

import { createBrowserClient } from "@supabase/ssr";

import { supabaseConfig } from "./config";

export function createClient() {
  const { url, key } = supabaseConfig();
  return createBrowserClient(url, key);
}

/** The signed-in user's access token, to send to our backend. Null when signed out. */
export async function getAccessToken(): Promise<string | null> {
  const { data } = await createClient().auth.getSession();
  return data.session?.access_token ?? null;
}
