"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import {
  askTutor,
  isDemoLimitReached,
  redeemInvite,
  streamTutor,
  type TutorMessage,
} from "@/lib/api";
import { getAccessToken } from "@/lib/supabase/client";
import { DemoLimitBanner } from "./DemoLimitBanner";
import { Markdown } from "./Markdown";

const FALLBACK = "I couldn't put an answer together just now. Try asking again.";

// A few openers so a first-time user knows the kind of thing to ask.
const SUGGESTIONS = ["How am I doing?", "Am I diversified?", "Am I beating the market?"];

/**
 * The tutor conversation. Lives inside TutorPanel, which is mounted in the root layout, so
 * the thread survives moving between pages and is only lost on a full reload. That matches
 * the design: nothing is stored server-side, the whole thread is re-sent each turn.
 *
 * Fills its container rather than sizing itself, because the panel owns the height.
 */
export function Tutor({
  pending,
  onPendingHandled,
  messagesLeft = null,
}: {
  pending?: { text: string; key: number } | null;
  /** Called once the pending question has been taken, so it can't be asked twice. */
  onPendingHandled?: () => void;
  /** A demo account's remaining questions, or null for a full account with no cap. */
  messagesLeft?: number | null;
}) {
  const [messages, setMessages] = useState<TutorMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Tracked locally as well as from the server: the layout that fetched the count doesn't
  // re-render when a question is asked, so the panel counts its own down and only reloads
  // the server's answer when the tier actually changes.
  const [left, setLeft] = useState<number | null>(messagesLeft);
  const router = useRouter();
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const sendRef = useRef<(text: string) => void>(() => {});
  const handledKey = useRef<number | null>(null);

  // In a fixed-height panel a new answer lands below the fold, so follow it down.
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages, busy]);

  // Opening the panel should put the cursor where you're about to type.
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // A demo account counts down; a full one stays null and never spends anything.
  const spend = () => setLeft((n) => (n === null ? null : Math.max(0, n - 1)));

  async function send(text: string) {
    const question = text.trim();
    // Out of questions is a dead end here, not an error: the banner below the thread is
    // already saying so, and an "explain this" button elsewhere shouldn't fire into a 403.
    if (question === "" || busy || left === 0) return;

    const next: TutorMessage[] = [...messages, { role: "user", content: question }];
    setMessages(next);
    setInput("");
    setError(null);
    setBusy(true);

    // Show an assistant bubble straight away and fill it as tokens stream in. It renders only
    // once it has content (see the render below), so the "Thinking…" line covers the wait.
    let answer = "";
    const show = (content: string) => setMessages([...next, { role: "assistant", content }]);
    show("");

    try {
      await streamTutor(next, await getAccessToken(), (delta) => {
        answer += delta;
        show(answer);
      });
      if (answer === "") show(FALLBACK); // the model returned nothing
      spend();
    } catch (e) {
      if (answer !== "") {
        // Some of the reply had already arrived; keep it and note it stopped short.
        setError("The tutor stopped partway. Try asking again.");
        return;
      }
      // Nothing streamed: fall back to the non-streaming endpoint before giving up.
      try {
        const { reply } = await askTutor(next, await getAccessToken());
        show(reply);
        spend();
      } catch (fallbackError) {
        setMessages(next); // drop the empty bubble
        // Out of questions isn't a failure, it's the end of the allowance, so it gets the
        // banner rather than a red line. Checked on both errors because the stream is what
        // refused first and the fallback only repeated it.
        if (isDemoLimitReached(fallbackError) || isDemoLimitReached(e)) {
          setLeft(0);
          return;
        }
        setError(
          fallbackError instanceof Error
            ? fallbackError.message
            : e instanceof Error
              ? e.message
              : "The tutor couldn't answer just now.",
        );
      }
    } finally {
      setBusy(false);
    }
  }

  // Keep a live pointer to the latest send, so the auto-send effect needn't depend on it.
  useEffect(() => {
    sendRef.current = send;
  });

  // An "explain this" button elsewhere can hand us a question. Send it once (keyed so
  // React's dev double-run doesn't fire it twice), after any in-flight answer finishes.
  //
  // Telling the panel we've taken it is what makes it a genuine one-shot. This component is
  // unmounted whenever the panel closes, so `handledKey` is gone by the time it reopens while
  // the question, which lives in the panel, is not. Without this the same question fired again
  // on every reopen, forever.
  useEffect(() => {
    if (pending && pending.key !== handledKey.current && !busy) {
      handledKey.current = pending.key;
      onPendingHandled?.();
      void sendRef.current(pending.text);
    }
  }, [pending, busy, onPendingHandled]);

  // Trade a code for an uncapped tutor. Redeeming is forgiving by design, so a wrong code
  // comes back ok and still on the demo tier; that's what tells us it didn't work.
  async function upgrade(code: string): Promise<string | null> {
    try {
      const { is_demo } = await redeemInvite(code, await getAccessToken());
      if (is_demo) return "That code didn't unlock it. Check it and try again.";
    } catch (e) {
      return e instanceof Error ? e.message : "That didn't work. Try again.";
    }
    setLeft(null);
    // The layout read the old tier on its last render, so refresh it rather than leaving the
    // rest of the app believing this is still a demo account.
    router.refresh();
    return null;
  }

  // Show "Thinking…" only until the first token lands, not through the whole stream.
  const last = messages[messages.length - 1];
  const waiting = busy && (last?.role !== "assistant" || last.content === "");

  return (
    <div className="flex h-full flex-col">
      <div className="shrink-0 border-b border-zinc-200 px-5 py-3 dark:border-zinc-800">
        <p className="text-xs text-zinc-500">
          It reads your real portfolio and explains it in plain English. A simulation for learning,
          not financial advice.
        </p>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
        {messages.length === 0 ? (
          <div className="space-y-3">
            <p className="text-sm text-zinc-500">
              Ask anything about what you own, how you&apos;re doing, or what a term means.
            </p>
            <div className="flex flex-wrap gap-2">
              {SUGGESTIONS.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => void send(suggestion)}
                  disabled={busy}
                  className="rounded-full border border-zinc-200 px-3 py-1 text-xs text-zinc-600 hover:bg-zinc-50 disabled:opacity-40 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {messages.map((message, index) =>
              message.role === "user" ? (
                <div key={index} className="text-right">
                  <span className="inline-block max-w-[85%] rounded-2xl bg-zinc-900 px-3 py-2 text-sm whitespace-pre-wrap text-white dark:bg-white dark:text-zinc-900">
                    {message.content}
                  </span>
                </div>
              ) : message.content === "" ? null : ( // an assistant bubble waiting for its first token
                <div key={index} className="text-left">
                  <div className="inline-block max-w-[85%] rounded-2xl bg-zinc-100 px-3 py-2 text-zinc-800 dark:bg-zinc-900 dark:text-zinc-100">
                    <Markdown>{message.content}</Markdown>
                  </div>
                </div>
              ),
            )}
          </div>
        )}

        {waiting && <p className="text-xs text-zinc-400">Thinking…</p>}
        {error && <p className="text-sm text-red-500">{error}</p>}
        <div ref={endRef} />
      </div>

      {left === 0 ? (
        <DemoLimitBanner onUpgrade={upgrade} />
      ) : (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void send(input);
          }}
          className="shrink-0 border-t border-zinc-200 px-5 py-3 dark:border-zinc-800"
        >
          <div className="flex items-center gap-2">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Ask about your portfolio…"
              aria-label="Ask the tutor a question"
              className="w-full bg-transparent text-sm outline-none"
            />
            <button
              type="submit"
              disabled={busy || input.trim() === ""}
              className="rounded-lg bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-40 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
            >
              Ask
            </button>
          </div>
          {/* Say the allowance up front rather than letting it run out as a surprise. */}
          {left !== null && (
            <p className="mt-1.5 text-xs text-zinc-400">
              {left === 1 ? "One question" : `${left} questions`} left on the demo code.
            </p>
          )}
        </form>
      )}
    </div>
  );
}
