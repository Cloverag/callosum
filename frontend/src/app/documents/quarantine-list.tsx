"use client";

import { ShieldAlert } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { FAILURE_REASON_LABEL, type QuarantineItem } from "@/lib/documents";

/**
 * Extractions the verifier refused, kept rather than deleted.
 *
 * ---------------------------------------------------------------------------
 * WHY THIS RENDERS THE QUOTE AND NOT A COUNT
 * ---------------------------------------------------------------------------
 * "4 items quarantined" is a summary, and summarising is the one thing this product
 * exists not to do to evidence. The quote is what the verifier actually looked at when
 * it refused the edge; without it a reader cannot tell a fabricated citation from a
 * paraphrase from a model naming an entity it never extracted.
 *
 * It is also the surface where quarantine stops looking like a malfunction. A rejected
 * extraction is the mechanism working — the process refusing to put an unevidenced
 * claim into institutional memory — and a bare error count communicates the opposite.
 *
 * Clearance-filtered by the API, not here. A quarantined quote is a verbatim span of a
 * source document, so it carries that document's sensitivity.
 */
export function QuarantineList({ items }: { items: QuarantineItem[] | null }) {
  if (items === null) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="h-24 rounded-[16px] bg-surface-sunken" />
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <Card className="px-6 py-12 text-center">
        <span className="mx-auto flex size-10 items-center justify-center rounded-full border border-border bg-surface-elevated text-muted-foreground">
          <ShieldAlert className="size-5" />
        </span>
        <h3 className="mt-3 text-sm font-medium text-foreground">Nothing quarantined</h3>
        <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">
          Every extracted fact so far carried a quote the verifier could locate in its
          source. Rejections are kept here rather than discarded, so this staying empty
          is a result and not an absence of checking.
        </p>
      </Card>
    );
  }

  return (
    <ul className="space-y-3">
      {items.map((item) => (
        <li key={item.id}>
          <Card className="p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <p className="font-mono text-[13px] text-foreground">
                {item.source} <span className="text-accent-emphasis">{item.relation}</span> {item.target}
              </p>
              <Badge tone="warning">{FAILURE_REASON_LABEL[item.reason] ?? item.reason}</Badge>
            </div>

            {/* The quote the model offered as evidence. Rendered verbatim and marked
                as a quotation, because the whole finding is that this text either was
                not in the source or did not support the claim. */}
            {item.quote ? (
              <blockquote className="mt-3 border-l-2 border-border-strong pl-3 text-sm italic text-muted-foreground">
                “{item.quote}”
              </blockquote>
            ) : (
              <p className="mt-3 text-sm text-subtle-foreground">No quote was offered.</p>
            )}

            {item.detail && <p className="mt-3 text-sm text-muted-foreground">{item.detail}</p>}

            <p className="mt-3 text-xs text-subtle-foreground">
              {/* Provenance, because "the model got it wrong" is only actionable if you
                  know which model. This is the same stamp the graph carries. */}
              {item.provider} · {item.extractor_model} · confidence {item.confidence.toFixed(2)}
            </p>
          </Card>
        </li>
      ))}
    </ul>
  );
}
