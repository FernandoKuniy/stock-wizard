// Supabase connection details. Both are public: the URL locates the project and the
// publishable key only lets a caller start an auth flow. Neither is a secret.
//
// These have to be read as literal `process.env.NEXT_PUBLIC_*` expressions. Next.js
// inlines them into the browser bundle by static substitution at build time, so a
// dynamic lookup like process.env[name] would come back undefined in the browser.

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const SUPABASE_PUBLISHABLE_KEY = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "";

/**
 * The project URL and publishable key, or a clear error if they aren't set.
 *
 * Checked here, when a client is built, rather than at module load: the app has to
 * survive being imported by `next build` in CI, where no environment is configured.
 */
export function supabaseConfig(): { url: string; key: string } {
  if (!SUPABASE_URL || !SUPABASE_PUBLISHABLE_KEY) {
    throw new Error(
      "Supabase isn't set up. Copy web/.env.example to web/.env.local and fill in " +
        "NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY from your " +
        "project's API settings.",
    );
  }
  return { url: SUPABASE_URL, key: SUPABASE_PUBLISHABLE_KEY };
}
