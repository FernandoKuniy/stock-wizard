import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";

import { TickerSearch } from "@/components/TickerSearch";
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

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <header className="border-b border-zinc-200 dark:border-zinc-800">
          <div className="mx-auto flex w-full max-w-4xl items-center gap-4 px-6 py-3">
            <Link href="/" className="font-semibold tracking-tight whitespace-nowrap">
              Stock Wizard
            </Link>
            <div className="flex-1">
              <TickerSearch />
            </div>
          </div>
        </header>
        {children}
      </body>
    </html>
  );
}
