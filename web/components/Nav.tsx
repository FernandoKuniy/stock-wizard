"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * The three places your money lives, one job each.
 *
 * The dashboard used to stack everything on one page, which meant the first screen was
 * answering five questions at once. Splitting it lets the overview answer only "how am I
 * doing?", and puts everything else one deliberate click away. Three destinations, not more:
 * a beginner should be choosing between three things, not thirty.
 */
const TABS = [
  { href: "/", label: "Overview" },
  { href: "/holdings", label: "Holdings" },
  { href: "/activity", label: "Activity" },
] as const;

export function Nav() {
  const pathname = usePathname();

  return (
    <nav aria-label="Your account" className="mx-auto w-full max-w-4xl px-6">
      <div className="flex gap-6">
        {TABS.map(({ href, label }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={`-mb-px border-b-2 py-2.5 text-sm transition-colors ${
                active
                  ? "border-zinc-900 font-medium text-zinc-900 dark:border-zinc-100 dark:text-zinc-100"
                  : "border-transparent text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
              }`}
            >
              {label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
