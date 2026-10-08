// "From page N" for a card generated with retrieval, expanding to the passage
// it was generated from. Renders nothing for cards with no sources (full-mode
// generation, hand-written cards), so callers need not check.

function pageLabel({ page_start, page_end }) {
  return page_start === page_end ? `${page_start}` : `${page_start}–${page_end}`;
}

export default function SourceCitation({ sources, className = "" }) {
  if (!sources || sources.length === 0) return null;

  const labels = [...new Set(sources.map(pageLabel))];
  const plural = labels.length > 1 || labels[0].includes("–");
  const summary = `From page${plural ? "s" : ""} ${labels.join(", ")}`;

  return (
    <details
      className={`collapse collapse-arrow rounded-lg border border-base-300 bg-base-200/40 ${className}`}
    >
      {/* Compact title, so the arrow is re-centred: DaisyUI places it at
          1.9rem, which suits its default 3.75rem title, not this one. */}
      <summary className="collapse-title min-h-0 py-2.5 pl-4 pr-10 text-xs font-medium text-base-content/60 after:!top-[1.25rem]">
        <span aria-hidden="true">📄 </span>
        {summary}
      </summary>
      <div className="collapse-content space-y-3 px-4 text-sm">
        {sources.map((s) => (
          <figure key={s.chunk_id}>
            {sources.length > 1 && (
              <figcaption className="mb-1 text-xs text-base-content/40">
                Page{s.page_start === s.page_end ? "" : "s"} {pageLabel(s)}
              </figcaption>
            )}
            <blockquote className="border-l-2 border-primary/40 pl-3 leading-relaxed text-base-content/70">
              {s.snippet}
            </blockquote>
          </figure>
        ))}
      </div>
    </details>
  );
}
