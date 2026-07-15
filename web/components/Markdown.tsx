import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

// The tutor replies in Markdown. Tailwind's preflight strips heading and list defaults, so
// each element is styled explicitly here (compact, chat-sized) rather than pulling in the
// typography plugin. Raw HTML is never rendered (no rehype-raw), so this stays XSS-safe.
const COMPONENTS: Components = {
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  ul: ({ children }) => <ul className="list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal space-y-1 pl-5">{children}</ol>,
  h1: ({ children }) => <h3 className="text-sm font-semibold">{children}</h3>,
  h2: ({ children }) => <h3 className="text-sm font-semibold">{children}</h3>,
  h3: ({ children }) => <h3 className="text-sm font-semibold">{children}</h3>,
  h4: ({ children }) => <h4 className="text-sm font-semibold">{children}</h4>,
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="underline">
      {children}
    </a>
  ),
  code: ({ children }) => (
    <code className="rounded bg-zinc-200 px-1 py-0.5 text-xs dark:bg-zinc-800">{children}</code>
  ),
  hr: () => <hr className="border-zinc-200 dark:border-zinc-700" />,
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-zinc-300 pl-3 text-zinc-600 dark:border-zinc-600 dark:text-zinc-400">
      {children}
    </blockquote>
  ),
  table: ({ children }) => (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border-b border-zinc-300 py-1 pr-3 font-semibold dark:border-zinc-600">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border-b border-zinc-200 py-1 pr-3 dark:border-zinc-800">{children}</td>
  ),
};

/** Render a Markdown string as styled, safe HTML. Block gaps come from the wrapper's space-y. */
export function Markdown({ children }: { children: string }) {
  return (
    <div className="space-y-2 text-sm leading-relaxed break-words">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
