"use client";

import { useEffect, useState } from "react";
import { FileText, Lock } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { FieldValue } from "@/components/ui/field-value";
import { withheld as withheldState } from "@/lib/field-state";
import { ApiError } from "@/lib/http";
import { cn } from "@/lib/utils";
import { SENSITIVITY_LABEL } from "@/lib/documents";
import { meetingsApi, type MeetingMaterial } from "@/lib/meetings";

/**
 * The source material assigned to one meeting.
 *
 * ---------------------------------------------------------------------------
 * WHY THIS SHOWS A COUNT WHEN THE VERSION CHAIN DOES AND THE DOCUMENT LIST DOES NOT
 * ---------------------------------------------------------------------------
 * ADR-018: a withheld item is disclosed as a count when a reader would otherwise
 * mistake a partial view for a complete one, and erased when the collection makes no
 * completeness claim.
 *
 * This list claims to be *the material for this meeting*. Someone reads it to prepare,
 * and a list that silently dropped two contracts sends them into the room believing
 * they are prepared. `/documents` is a browse view and makes no such claim, which is
 * why it erases — the two are on opposite sides of the rule on purpose.
 *
 * The count goes through `FieldValue`'s `withheld` state rather than bespoke copy, for
 * the reason `version-chain.tsx` gives: a second phrasing of the same disclosure is how
 * two surfaces come to tell a reader different things about the same fact.
 *
 * ---------------------------------------------------------------------------
 * WHAT THIS COMPONENT NEVER RECEIVES
 * ---------------------------------------------------------------------------
 * There is no withheld-item placeholder to render, because the server sends no rows for
 * withheld material — only the integer. That is deliberate: a per-item placeholder
 * would restore the position information the count is designed to replace, and a
 * component holding a title it must not render is one careless edit from rendering it.
 */
export function MaterialList({ meetingId, className }: { meetingId: string; className?: string }) {
  const [material, setMaterial] = useState<MeetingMaterial | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    let live = true;
    setMaterial(null);
    setError(null);
    meetingsApi
      .material(meetingId)
      .then((m) => live && setMaterial(m))
      .catch(
        (e) =>
          live &&
          setError(e instanceof ApiError ? e : new ApiError(0, "network", "Could not reach the server.")),
      );
    return () => {
      live = false;
    };
  }, [meetingId]);

  if (error) {
    return (
      <p className={cn("text-sm text-muted-foreground", className)} role="status">
        The material for this meeting could not be loaded. {error.message}
      </p>
    );
  }

  if (material === null) {
    return (
      <div className={cn("space-y-2", className)} aria-busy="true">
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="h-10 rounded-[12px] bg-surface-sunken" />
        ))}
      </div>
    );
  }

  // Nothing assigned AND nothing withheld — the genuinely empty case. Distinct from
  // the all-withheld case below, which looks identical in the list and is not empty at
  // all; conflating them is exactly the failure ADR-018 names.
  if (material.documents.length === 0 && material.withheld === 0) {
    return (
      <p className={cn("text-sm text-muted-foreground", className)}>
        No material has been assigned to this meeting yet.
      </p>
    );
  }

  return (
    <div className={cn("space-y-3", className)}>
      {material.documents.length > 0 && (
        <ul className="space-y-1.5">
          {material.documents.map((doc) => (
            <li
              key={doc.id}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-[12px] border border-border bg-surface-sunken px-3 py-2"
            >
              <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              {/* `basis-[18rem]` with wrapping, not `min-w-0` — a long title collapsed
                  to two characters once already on /documents (f7fdfb4). */}
              <span className="flex-1 basis-[18rem] truncate text-sm text-foreground">{doc.title}</span>
              {doc.revision > 1 && (
                <span className="tabular-nums text-xs font-semibold text-muted-foreground">
                  v{doc.revision}
                </span>
              )}
              <Badge tone="neutral">{SENSITIVITY_LABEL[doc.sensitivity]}</Badge>
            </li>
          ))}
        </ul>
      )}

      {material.withheld > 0 && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Lock className="size-4 shrink-0" aria-hidden="true" />
          <FieldValue state={withheldState<number>(material.withheld)} />
          <span>
            {material.withheld === 1 ? "document is" : "documents are"} above your clearance.
            This list is not everything the board holds for this meeting.
          </span>
        </p>
      )}
    </div>
  );
}
