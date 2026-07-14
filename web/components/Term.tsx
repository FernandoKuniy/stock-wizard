"use client";

import { useId, useState } from "react";

import { GLOSSARY, type GlossaryTerm } from "@/lib/glossary";

/**
 * A jargon word with its plain-English meaning one hover or tap away.
 *
 * Works on a mouse (hover), a keyboard (focus), and a phone (tap), because a beginner
 * on a phone needs the definition just as much as anyone.
 */
export function Term({ name, children }: { name: GlossaryTerm; children?: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();

  return (
    <span className="relative inline-block">
      <button
        type="button"
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        onClick={() => setOpen((was) => !was)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className="cursor-help underline decoration-dotted decoration-zinc-400 underline-offset-4 hover:decoration-zinc-600 dark:hover:decoration-zinc-300"
      >
        {children ?? name}
      </button>

      {open && (
        <span
          id={id}
          role="tooltip"
          className="absolute bottom-full left-1/2 z-20 mb-2 w-64 -translate-x-1/2 rounded-lg border border-zinc-200 bg-white p-3 text-left text-xs leading-relaxed font-normal text-zinc-600 shadow-lg dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
        >
          {GLOSSARY[name]}
        </span>
      )}
    </span>
  );
}
