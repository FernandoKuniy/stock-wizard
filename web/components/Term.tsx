"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { GLOSSARY, type GlossaryTerm } from "@/lib/glossary";

type TooltipCoords = {
  top: number;
  left: number;
};

/**
 * A jargon word with its plain-English meaning one hover or tap away.
 *
 * Works on a mouse (hover), a keyboard (focus), and a phone (tap), because a beginner
 * on a phone needs the definition just as much as anyone.
 *
 * The bubble is portalled to <body> and positioned in viewport coordinates, because the
 * table it usually sits in clips its own overflow. Positioned inline, the definition would
 * get cut off by the very element it is trying to explain.
 */
export function Term({ name, children }: { name: GlossaryTerm; children?: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<TooltipCoords | null>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const id = useId();

  const updateCoords = useCallback(() => {
    const button = buttonRef.current;
    if (!button) return;

    const rect = button.getBoundingClientRect();
    setCoords({
      top: rect.top - 8,
      left: rect.left + rect.width / 2,
    });
  }, []);

  // Measure whenever it opens, whichever way it was opened (hover, focus, or tap), and keep
  // it pinned to the word if the page moves underneath it.
  useEffect(() => {
    if (!open) return;

    const reposition = () => updateCoords();
    window.addEventListener("scroll", reposition, true);
    window.addEventListener("resize", reposition);

    return () => {
      window.removeEventListener("scroll", reposition, true);
      window.removeEventListener("resize", reposition);
    };
  }, [open, updateCoords]);

  const show = useCallback(() => {
    updateCoords();
    setOpen(true);
  }, [updateCoords]);

  // No "mounted" guard needed: `open` only ever flips from a user event, which cannot happen
  // during server rendering, so document.body is always there by the time we portal into it.
  const tooltip =
    open && coords
      ? createPortal(
          <span
            id={id}
            role="tooltip"
            style={{ top: coords.top, left: coords.left }}
            className="pointer-events-none fixed z-50 w-64 -translate-x-1/2 -translate-y-full rounded-lg border border-zinc-200 bg-white p-3 text-left text-xs leading-relaxed font-normal text-zinc-600 shadow-lg dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
          >
            {GLOSSARY[name]}
          </span>,
          document.body,
        )
      : null;

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        // Measure on the way open, not just on hover: a tap never fires onMouseEnter, so
        // without this the definition would never show up on a phone.
        onClick={() => (open ? setOpen(false) : show())}
        onMouseEnter={show}
        onMouseLeave={() => setOpen(false)}
        onFocus={show}
        onBlur={() => setOpen(false)}
        className="cursor-help underline decoration-dotted decoration-zinc-400 underline-offset-4 hover:decoration-zinc-600 dark:hover:decoration-zinc-300"
      >
        {children ?? name}
      </button>
      {tooltip}
    </>
  );
}
