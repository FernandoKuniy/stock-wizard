import type { Metadata } from "next";
import { Geist } from "next/font/google";
import Link from "next/link";

import { BrandMark } from "@/components/BrandMark";
import { CalmToggle } from "@/components/CalmToggle";
import { Nav } from "@/components/Nav";
import { TickerSearch } from "@/components/TickerSearch";
import { TutorPanel } from "@/components/TutorPanel";
import { getMe } from "@/lib/api";
import { getAccessToken, getUser } from "@/lib/supabase/server";
import { signOut } from "./login/actions";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const description =
  "Learn investing with fake money and real market prices. A simulation for education, not financial advice.";

// Social cards need absolute URLs, so Next needs a base to resolve them against. The deployed
// site is the default: a preview build with no env var set should still advertise the real
// thing rather than localhost.
const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? "https://stockwiz.vercel.app";

// `opengraph-image.tsx` fills in the image tags for both cards on its own, so there's no
// image to name here.
export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: "Stock Wizard",
  description,
  openGraph: {
    type: "website",
    url: "/",
    siteName: "Stock Wizard",
    title: "Stock Wizard",
    description,
  },
  twitter: {
    card: "summary_large_image",
    title: "Stock Wizard",
    description,
  },
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Signed out, the only page you can reach is the login screen, so the header is
  // just the wordmark. No search box, no nav, nothing to sign out of.
  const user = await getUser();

  // A signed-in user who hasn't redeemed an invite code yet is on the redeem screen, which
  // should look as bare as the login screen: wordmark and a way out, but none of the app's
  // search, nav, or tutor. `provisioned` is what tells the two apart. If the probe fails we
  // fall back to hiding the chrome, since it wouldn't work without an account anyway.
  let provisioned = false;
  // Null for a full account (no cap) and a count for a demo one, which is what the tutor
  // panel needs to show the allowance and swap in the "ask me for a code" banner at zero.
  let tutorMessagesLeft: number | null = null;
  if (user) {
    try {
      const me = await getMe(await getAccessToken());
      provisioned = me.provisioned;
      tutorMessagesLeft = me.tutor_messages_left;
    } catch {
      provisioned = false;
    }
  }

  return (
    <html lang="en" className={`${geistSans.variable} h-full antialiased`}>
      <head>
        {/* Set calm mode before the first paint. Doing it in an effect would flash the
            balance on every load, which is the exact thing calm mode exists to prevent. */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              "try{if(localStorage.getItem('stockwizard.calm')==='on')" +
              "document.documentElement.dataset.calm='on'}catch(e){}",
          }}
        />
      </head>
      <body className="flex min-h-full flex-col">
        <header className="border-b border-zinc-200 dark:border-zinc-800">
          <div className="mx-auto flex w-full max-w-4xl items-center gap-4 px-6 py-3">
            <Link
              href="/"
              className="flex items-center gap-2 font-semibold tracking-tight whitespace-nowrap"
            >
              <BrandMark />
              Stock Wizard
            </Link>
            {/* Search only makes sense once you're in. Keep the spacer either way so Sign
                out stays pinned to the right. */}
            {provisioned ? (
              <div className="flex-1">
                <TickerSearch />
              </div>
            ) : (
              <div className="flex-1" />
            )}
            {user && (
              <form action={signOut}>
                <button
                  type="submit"
                  className="text-sm whitespace-nowrap text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
                >
                  Sign out
                </button>
              </form>
            )}
          </div>
          {provisioned && (
            <div className="mx-auto flex w-full max-w-4xl items-center justify-between gap-4 px-6">
              <Nav />
              <div className="flex items-center gap-2">
                <CalmToggle />
                <TutorPanel messagesLeft={tutorMessagesLeft} />
              </div>
            </div>
          )}
        </header>
        {children}
        <footer className="border-t border-zinc-100 px-6 py-6 text-center text-xs text-zinc-500 dark:border-zinc-800">
          A simulation for learning, not financial advice. Real market prices, pretend money.
        </footer>
      </body>
    </html>
  );
}
