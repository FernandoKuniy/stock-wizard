// The Supabase client for code running on the server (Server Components and Actions).

import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

import { supabaseConfig } from "./config";

export async function createClient() {
  const cookieStore = await cookies();
  const { url, key } = supabaseConfig();

  return createServerClient(url, key, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) => cookieStore.set(name, value, options));
        } catch {
          // A Server Component can read cookies but not set them. The proxy already
          // refreshed the session on this request, so there is nothing to do here.
        }
      },
    },
  });
}

/**
 * The signed-in user's access token, to send to our backend. Null when signed out.
 *
 * This reads the token straight from the session cookie without verifying it, which
 * is fine because we are only forwarding it: the FastAPI backend checks the signature
 * itself. Never use it to decide, here in the frontend, who someone is. For that, ask
 * Supabase with getClaims() (see proxy.ts).
 */
export async function getAccessToken(): Promise<string | null> {
  const supabase = await createClient();
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

/** The signed-in user's verified claims, or null when signed out. */
export async function getUser(): Promise<{ email: string } | null> {
  const supabase = await createClient();
  const { data } = await supabase.auth.getClaims();
  const claims = data?.claims;
  if (!claims) return null;
  return { email: typeof claims.email === "string" ? claims.email : "" };
}
