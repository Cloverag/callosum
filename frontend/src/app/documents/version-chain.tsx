"use client";

import { useEffect, useState } from "react";
import { History } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { FieldValue } from "@/components/ui/field-value";
import { withheld as withheldState } from "@/lib/field-state";
import { ApiError } from "@/lib/http";
import { loadFailedText } from "@/lib/error-text";
import { cn } from "@/lib/utils";
import { documentsApi, SENSITIVITY_LABEL, type Document, type DocumentChain } from "@/lib/documents";

/**
 * One document's revision history.
 *
 * ---------------------------------------------------------------------------
 * WHY A WITHHELD REVISION IS A COUNT AND NOTHING ELSE
 * ---------------------------------------------------------------------------
 * A revision may sit ABOVE its predecessor's sensitivity — `supersede_document` refuses
 * a downgrade, not an upgrade — so a chain a reader can enter may continue past their
 * clearance. `rules.md` §2 and P4's exit criterion both say what happens then: the count
 * is disclosed and nothing else. No title, no date, no id.
 *
 * The count is rendered through `FieldValue`'s `withheld` state rather than as bespoke
 * copy. That state exists precisely for this ("N withheld at your clearance. The answer
 * may be incomplete."), and a second phrasing of the same disclosure is how two surfaces
 * end up telling a reader different things about the same fact.
 *
 * ---------------------------------------------------------------------------
 * THE HONEST FAILURE: "CURRENT" IS SOMETIMES UNKNOWABLE
 * ---------------------------------------------------------------------------
 * When the newest revision is withheld the API returns `current_id: null`, and this
 * component says so rather than marking the newest READABLE revision as current. That
 * substitution is the whole feature inverted: it would badge a document the board has
 * already corrected as the one in force, and the reader would have no signal at all.
 * "You cannot see the current revision" is worse news and a true statement.
 */
export function VersionChain({ document, className }: { document: Document; className?: string }) {
  const [chain, setChain] = useState<DocumentChain | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    let live = true;
    setChain(null);
    setError(null);
    documentsApi
      .versions(document.id)
      .then((c) => live && setChain(c))
      .catch((e) => live && setError(e instanceof ApiError ? e : new ApiError(0, "network", "Could not reach the server.")));
    return () => {
      live = false;
    };
  }, [document.id]);

  if (error) {
    return (
      <p className={cn("text-sm text-muted-foreground", className)} role="status">
        {loadFailedText("The revision history", error)}
      </p>
    );
  }

  if (chain === null) {
    return (
      <div className={cn("space-y-2", className)} aria-busy="true">
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="h-10 rounded-[12px] bg-surface-sunken" />
        ))}
      </div>
    );
  }

  // State 2 of the seven. A chain of one is not an empty state — it is the ordinary
  // case for every document nobody has needed to correct, and saying "no revisions"
  // about it would read as something missing.
  if (chain.revisions.length === 1 && chain.withheld === 0) {
    return (
      <p className={cn("text-sm text-muted-foreground", className)}>
        This is the only revision. Filing a correction creates a new revision and links
        it here; the original is never edited.
      </p>
    );
  }

  return (
    <div className={cn("space-y-3", className)}>
      <ol className="space-y-1.5">
        {chain.revisions.map((revision) => {
          const isCurrent = revision.id === chain.current_id;
          return (
            <li
              key={revision.id}
              className={cn(
                "flex flex-wrap items-center gap-x-3 gap-y-1 rounded-[12px] border px-3 py-2",
                isCurrent ? "border-accent-border bg-accent-subtle" : "border-border bg-surface-sunken",
              )}
            >
              <span className="tabular-nums text-xs font-semibold text-muted-foreground">
                v{revision.revision}
              </span>
              <span className="min-w-0 flex-1 truncate text-sm text-foreground">{revision.title}</span>
              <Badge tone="neutral">{SENSITIVITY_LABEL[revision.sensitivity]}</Badge>
              <span className="tabular-nums text-xs text-subtle-foreground">
                {new Date(revision.ingested_at).toLocaleDateString(undefined, {
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                })}
              </span>
              {isCurrent && <Badge tone="accent">Current</Badge>}
            </li>
          );
        })}
      </ol>

      {chain.withheld > 0 && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <History className="size-4 shrink-0" aria-hidden="true" />
          {/* The count, in the vocabulary the rest of the product already uses for it. */}
          <FieldValue state={withheldState<number>(chain.withheld)} />
          <span>
            {chain.withheld === 1 ? "later revision is" : "later revisions are"} above your
            clearance.
          </span>
        </p>
      )}

      {chain.current_id === null && (
        <p role="status" className="rounded-[12px] border border-warning bg-surface-sunken px-3 py-2 text-sm text-foreground">
          The current revision is not visible to you. What you can see above has been
          superseded — do not act on it as the document in force.
        </p>
      )}
    </div>
  );
}
