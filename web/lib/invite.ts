/**
 * Carrying the invite code across the email confirmation.
 *
 * Signing up and being let into the app are two different steps, and an email confirmation
 * sits between them: at signup there's no session yet, so the code can't be redeemed, and by
 * the time there is one the form that collected it is long gone. So the code rides along in
 * the Supabase user's metadata and is redeemed automatically once a session exists.
 *
 * IMPORTANT: `user_metadata` is writable by the user it belongs to, so nothing here is a
 * security check. It is a carrier, not a credential. The code is still verified server-side
 * against SIGNUP_CODE and DEMO_SIGNUP_CODE (see api/routers/account.py), and putting a made-up
 * value in metadata gets you exactly the same 403 as typing one into the form.
 */

/** The key the code travels under, in `options.data` at signup. */
export const INVITE_CODE_KEY = "invite_code";

/**
 * The invite code stashed on a Supabase user, or null if there isn't a usable one.
 *
 * Takes the metadata object rather than the user so it can be tested without building a
 * whole Supabase user, and tolerates the shapes reality produces: missing, null, the wrong
 * type, or whitespace someone pasted in with the code.
 */
export function inviteCodeFrom(metadata: unknown): string | null {
  if (typeof metadata !== "object" || metadata === null) return null;
  const value = (metadata as Record<string, unknown>)[INVITE_CODE_KEY];
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}
