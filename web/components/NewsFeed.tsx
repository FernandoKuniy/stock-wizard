import type { NewsItem } from "@/lib/api";
import { formatNewsDate } from "@/lib/format";

/**
 * Recent headlines for a stock, straight from the news provider. Just a scannable list that
 * links out to the source: the headlines are the source's words, not our figures, so we
 * attribute each one and send the reader to the original.
 */
export function NewsFeed({ items }: { items: NewsItem[] }) {
  if (items.length === 0) return null;

  return (
    <div className="rounded-xl border border-zinc-200 p-5 dark:border-zinc-800">
      <h2 className="text-sm font-medium">Recent news</h2>
      <ul className="mt-3 divide-y divide-zinc-100 dark:divide-zinc-800">
        {items.map((item, i) => {
          const date = formatNewsDate(item.date);
          return (
            <li key={item.url || i} className="py-3 first:pt-0 last:pb-0">
              <a href={item.url} target="_blank" rel="noopener noreferrer" className="group block">
                <div className="text-sm font-medium group-hover:underline">{item.headline}</div>
                <div className="mt-1 text-xs text-zinc-500">
                  {item.source}
                  {date && ` · ${date}`}
                </div>
              </a>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
