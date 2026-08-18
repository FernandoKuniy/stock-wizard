// A tiny bridge so an "explain this" button anywhere can open the tutor and ask it something.
//
// The tutor panel lives in the header and manages its own open state; a finding sits inside a
// page. Rather than thread a context through server components, a button dispatches a window
// event and the panel listens. It's the same "external store" instinct as the first-time
// callouts: a lightweight signal, no provider wrapping the tree.

const ASK_EVENT = "stockwizard:ask-tutor";

/** Open the tutor (if closed) and have it answer `prompt`. Client-side only. */
export function askTutorAbout(prompt: string): void {
  window.dispatchEvent(new CustomEvent<string>(ASK_EVENT, { detail: prompt }));
}

/** Subscribe to explain-this requests. Returns an unsubscribe function. */
export function onAskTutor(handler: (prompt: string) => void): () => void {
  const listener = (event: Event) => handler((event as CustomEvent<string>).detail);
  window.addEventListener(ASK_EVENT, listener);
  return () => window.removeEventListener(ASK_EVENT, listener);
}
