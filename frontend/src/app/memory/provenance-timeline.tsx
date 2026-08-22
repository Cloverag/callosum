"use client";

import { useMemo } from "react";
import { Lock } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { provenanceOf } from "@/lib/provenance";
import type { GraphView } from "@/lib/graph";

/**
 * How the memory was built, one source document at a time.
 *
 * This is a LENS, not a list: selecting a document highlights exactly what it
 * contributed in the canvas above and dims the rest, so "where did this come
 * from" is answered by looking rather than by reading a filename. Decisions are
 * separately clickable and jump straight to that node's evidence.
 *
 * The bar is contribution, on one shared scale across all rows, so a reader can
 * compare documents at a glance — three board transcripts do most of the work
 * and the rest add one or two edges each. That is the corpus being a capability
 * matrix rather than a pile of similar meetings, made visible.
 */
export function ProvenanceTimeline({
  view,
  activeDocument,
  onSelectDocument,
  onSelectNode,
}: {
  view: GraphView;
  activeDocument: string | null;
  onSelectDocument: (document: string | null) => void;
  onSelectNode: (id: string) => void;
}) {
  const entries = useMemo(() => provenanceOf(view), [view]);
  const maxContribution = Math.max(...entries.map((e) => e.entities + e.relationships), 1);

  return (
    <section aria-labelledby="provenance-heading" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 id="provenance-heading" className="text-sm font-semibold text-foreground">
          Provenance
        </h2>
        {activeDocument ? (
          <button
            type="button"
            onClick={() => onSelectDocument(null)}
            className="rounded-[6px] text-xs text-accent-emphasis underline decoration-dotted underline-offset-4 hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
          >
            Clear filter
          </button>
        ) : (
          <p className="text-xs text-subtle-foreground">
            Select a document to see what it contributed
          </p>
        )}
      </div>

      <ol className="flex flex-col">
        {entries.map((entry, i) => {
          const active = activeDocument === entry.document;
          const total = entry.entities + entry.relationships;

          return (
            <li key={entry.document} className="relative flex gap-3">
              {/* Timeline rule. The last item stops the line so it reads as an
                  end, not a truncation. */}
              <div className="flex flex-col items-center pt-4">
                <span
                  className={cn(
                    "size-2 shrink-0 rounded-full ring-2 ring-surface-raised",
                    active ? "bg-accent" : entry.restricted ? "bg-warning" : "bg-border-strong"
                  )}
                  aria-hidden
                />
                {i < entries.length - 1 && (
                  <span className="w-px flex-1 bg-border" aria-hidden />
                )}
              </div>

              <button
                type="button"
                onClick={() => onSelectDocument(active ? null : entry.document)}
                aria-pressed={active}
                className={cn(
                  "mb-1 flex-1 rounded-[12px] border px-3.5 py-3 text-left transition-colors",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface",
                  active
                    ? "border-accent-border bg-accent-subtle"
                    : "border-transparent hover:border-border hover:bg-surface-alt"
                )}
              >
                <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                  <span className="flex items-center gap-2 text-sm font-medium text-foreground">
                    {entry.label}
                    {/* `role="img"` is required: an aria-label on a bare <svg> is
                        not reliably exposed, because svg's implicit role varies by
                        engine. Without it the only signal that this row is
                        restricted is a colour and a glyph. */}
                    {entry.restricted && (
                      <Lock
                        className="size-3 text-warning-emphasis"
                        role="img"
                        aria-label="Restricted"
                      />
                    )}
                  </span>
                  <span className="text-xs tabular-nums text-muted-foreground">
                    +{entry.entities} entities · +{entry.relationships} relationships
                  </span>
                </div>

                {/* Contribution, one shared scale across every row.

                    Emphasis moves within the memory ramp rather than switching
                    to action blue: this bar is the value-bearing mark, and the
                    row already reads as active from its border, its wash and
                    its dot. Solid tokens rather than an `opacity: 0.5`
                    recession, which measured ~1.9:1 against the track — below
                    the 3:1 floor for a non-text mark — and whose ordering
                    inverted under the dark theme's reversed elevation. */}
                <div
                  className="mt-2 h-1 w-full overflow-hidden rounded-full bg-surface-sunken"
                  role="img"
                  aria-label={`Contributed ${total} records of ${maxContribution} at most`}
                >
                  <div
                    className={cn(
                      "h-full rounded-full",
                      active ? "bg-memory-emphasis" : "bg-memory-soft"
                    )}
                    style={{ width: `${(total / maxContribution) * 100}%` }}
                  />
                </div>

                <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-subtle-foreground">
                  <span className="uppercase tracking-[0.06em]">{entry.kind}</span>
                  {entry.types.map((t) => (
                    <span key={t.type}>
                      · {t.count} {t.label}
                      {t.count > 1 && !t.label.endsWith("s") ? "s" : ""}
                    </span>
                  ))}
                </div>

                {entry.decisions.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {entry.decisions.map((d) => (
                      // Nested interactive content inside a button is invalid, so
                      // these are spans with an explicit click handler and their
                      // own keyboard affordance.
                      <span
                        key={d}
                        role="button"
                        tabIndex={0}
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectNode(d);
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            e.stopPropagation();
                            onSelectNode(d);
                          }
                        }}
                        className="cursor-pointer rounded-full border border-memory-emphasis/35 bg-memory-subtle px-2 py-0.5 text-[11px] font-medium text-memory-emphasis hover:border-memory-emphasis/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised"
                      >
                        {d}
                      </span>
                    ))}
                  </div>
                )}
              </button>
            </li>
          );
        })}
      </ol>

      {view.withheldNodes > 0 && (
        <p className="text-xs text-subtle-foreground">
          One source is missing from this list at the current clearance — see the withheld
          count above.
        </p>
      )}

      <div className="flex items-center gap-2 pt-1">
        <Badge tone="neutral">{entries.length} sources</Badge>
        <span className="text-xs text-subtle-foreground">
          in the order they were ingested
        </span>
      </div>
    </section>
  );
}
