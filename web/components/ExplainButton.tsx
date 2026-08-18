"use client";

import { askTutorAbout } from "@/lib/tutor-bus";

/**
 * A small "ask the tutor about this" link that opens the tutor panel pre-loaded with a question.
 *
 * The prompt is deliberately qualitative (it names the topic, never a figure): the tutor fetches
 * the real numbers from its account-scoped tools, so what it says still comes from code, not from
 * whatever text the page happened to pass in. It explains an existing observation; it never
 * volunteers a buy-or-sell opinion (hard rule #2).
 */
export function ExplainButton({
  prompt,
  label = "Explain this to me",
}: {
  prompt: string;
  label?: string;
}) {
  return (
    <button
      type="button"
      onClick={() => askTutorAbout(prompt)}
      className="text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400"
    >
      {label} →
    </button>
  );
}
