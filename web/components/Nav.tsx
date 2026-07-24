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
    // `min-w-0` lets the nav shrink inside the header row (a flex item won't go below its
    // content width without it, which pushed the whole row off a 320px screen), and the
    // overflow is the safety valve: the tabs scroll rather than wrapping onto two lines.
    <nav aria-label="Your account" className="flex min-w-0 gap-4 overflow-x-auto sm:gap-6">
      {TABS.map(({ href, label }) => {
        const active = pathname === href;
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={`-mb-px shrink-0 border-b-2 py-2.5 text-sm whitespace-nowrap transition-colors ${
              active
                ? "border-zinc-900 font-medium text-zinc-900 dark:border-zinc-100 dark:text-zinc-100"
                : "border-transparent text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
            }`}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
