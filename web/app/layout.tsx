import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";

import { CalmToggle } from "@/components/CalmToggle";
import { Nav } from "@/components/Nav";
import { TickerSearch } from "@/components/TickerSearch";
import { TutorPanel } from "@/components/TutorPanel";
import { getUser } from "@/lib/supabase/server";
import { signOut } from "./login/actions";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Stock Wizard",
  description:
    "Learn investing with fake money and real market prices. A simulation for education, not financial advice.",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Signed out, the only page you can reach is the login screen, so the header is
  // just the wordmark. No search box, no nav, nothing to sign out of.
  const user = await getUser();

  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
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
            <Link href="/" className="font-semibold tracking-tight whitespace-nowrap">
              Stock Wizard
            </Link>
            {user && (
              <>
                <div className="flex-1">
                  <TickerSearch />
                </div>
                <form action={signOut}>
                  <button
                    type="submit"
                    className="text-sm whitespace-nowrap text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
                  >
                    Sign out
                  </button>
                </form>
              </>
            )}
          </div>
          {user && (
            <div className="mx-auto flex w-full max-w-4xl items-center justify-between gap-4 px-6">
              <Nav />
              <div className="flex items-center gap-2">
                <CalmToggle />
                <TutorPanel />
              </div>
            </div>
          )}
        </header>
        {children}
      </body>
    </html>
  );
}
