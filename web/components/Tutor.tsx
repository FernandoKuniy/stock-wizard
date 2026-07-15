"use client";

import { useState } from "react";

import { askTutor, type TutorMessage } from "@/lib/api";
import { getAccessToken } from "@/lib/supabase/client";
import { Markdown } from "./Markdown";

// A few openers so a first-time user knows the kind of thing to ask.
const SUGGESTIONS = ["How am I doing?", "Am I diversified?", "Am I beating the market?"];

export function Tutor() {
  const [messages, setMessages] = useState<TutorMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send(text: string) {
    const question = text.trim();
    if (question === "" || busy) return;

    const next: TutorMessage[] = [...messages, { role: "user", content: question }];
    setMessages(next);
    setInput("");
    setError(null);
    setBusy(true);
    try {
      const { reply } = await askTutor(next, await getAccessToken());
      setMessages([...next, { role: "assistant", content: reply }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The tutor couldn't answer just now.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-xl border border-zinc-200 dark:border-zinc-800">
      <div className="border-b border-zinc-200 px-5 py-3 dark:border-zinc-800">
        <h2 className="text-sm font-semibold">Ask the tutor</h2>
        <p className="mt-0.5 text-xs text-zinc-500">
          It reads your real portfolio and explains it in plain English. A simulation for learning,
          not financial advice.
        </p>
      </div>

      <div className="space-y-3 px-5 py-4">
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
              ) : (
                <div key={index} className="text-left">
                  <div className="inline-block max-w-[85%] rounded-2xl bg-zinc-100 px-3 py-2 text-zinc-800 dark:bg-zinc-900 dark:text-zinc-100">
                    <Markdown>{message.content}</Markdown>
                  </div>
                </div>
              ),
            )}
          </div>
        )}

        {busy && <p className="text-xs text-zinc-400">Thinking…</p>}
        {error && <p className="text-sm text-red-500">{error}</p>}
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          void send(input);
        }}
        className="flex items-center gap-2 border-t border-zinc-200 px-5 py-3 dark:border-zinc-800"
      >
        <input
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
      </form>
    </section>
  );
}
