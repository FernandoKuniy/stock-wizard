// Where the confirmation link in the signup email lands.
//
// This route is the whole reason clicking that link now signs you in. Without it the link
// pointed at the site root, the proxy saw no session, and bounced you to /login to sign in by
// hand and then type your invite code again on /redeem. Here we turn the token in the URL into
// a real session, redeem the code the user already gave us at signup, and drop them on the
// dashboard.
//
// It handles both shapes Supabase can send, so the flow works whether or not the email template
// has been updated:
//
//   - `token_hash` + `type`, from a template using {{ .TokenHash }}. Preferred, because it
//     verifies on its own and so survives the very common case of signing up on a laptop and
//     opening the email on a phone.
//   - `code`, from the default {{ .ConfirmationURL }} template. Works, but it's a PKCE exchange
//     against a verifier cookie set at signup, so it only succeeds in the same browser.

import { type EmailOtpType } from "@supabase/supabase-js";
import { redirect } from "next/navigation";
import { type NextRequest } from "next/server";

import { redeemInvite } from "@/lib/api";
import { inviteCodeFrom } from "@/lib/invite";
import { createClient } from "@/lib/supabase/server";

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const tokenHash = params.get("token_hash");
  const type = params.get("type") as EmailOtpType | null;
  const code = params.get("code");

  const supabase = await createClient();

  // A route handler can set cookies, so verifying here is what actually persists the session.
  let metadata: unknown = null;
  let token: string | null = null;

  if (tokenHash && type) {
    const { data, error } = await supabase.auth.verifyOtp({ type, token_hash: tokenHash });
    if (!error) {
      metadata = data.user?.user_metadata ?? null;
      token = data.session?.access_token ?? null;
    }
  } else if (code) {
    const { data, error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      metadata = data.user?.user_metadata ?? null;
      token = data.session?.access_token ?? null;
    }
  }

  // An expired or already-used link, or one opened in a different browser than it was
  // requested from. Nothing to do but let them sign in, which works fine now that the address
  // is confirmed. Deliberately vague: this page shouldn't say whether an address exists.
  if (!token) redirect("/login?confirmed=0");

  // They already typed a code at signup, so don't ask again. Redeeming is idempotent, so a
  // second click on the same link is harmless.
  const invite = inviteCodeFrom(metadata);
  if (invite) {
    try {
      await redeemInvite(invite, token);
    } catch {
      // A wrong code, or the API having a bad moment. They're signed in either way, so the
      // redeem screen can take it from here rather than stranding them on an error page.
      redirect("/redeem");
    }
  }

  redirect("/");
}
