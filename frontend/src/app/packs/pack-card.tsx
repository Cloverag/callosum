"use client";

import { ArrowRight, FileText, Lock, StickyNote } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  PACK_STATUS_LABEL,
  PACK_STATUS_TONE,
  resolveItems,
  supersededBy,
  type BoardPack,
} from "@/lib/packs";
import { DOC_TYPE_LABEL, SENSITIVITY_LABEL, type Document } from "@/lib/documents";

function formatDate(iso: string): string {
  // Pinned locale and zone: a date rendered from the browser's locale differs
  // between server and client and produces a hydration mismatch. Same fix as
  // the decisions and entity-conflicts pages.
  return new Date(iso).toLocaleDateString("en-US", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

/**
 * One board pack and the documents in it.
 *
 * ---------------------------------------------------------------------------
 * WHY THE ACCESS NOTICE IS UNCONDITIONAL
 * ---------------------------------------------------------------------------
 * The obvious design is to show "some content is unavailable" only when
 * something was actually withheld. That design cannot be built here, and should
 * not be.
 *
 * It cannot be built because the server renumbers items from 1 before sending
 * them (`meridian/packs.py:153-190`) and returns no total, so a withheld item
 * leaves no trace in the response. There is nothing to condition on.
 *
 * It should not be built because a conditional notice *is* a disclosure. Showing
 * it only when something is hidden tells the reader that this pack contains
 * material they are excluded from — one bit, but the bit that matters. For a
 * board pack that is a live signal: it says the board is reviewing something
 * about you, or without you. A count of zero and a count of one must be
 * indistinguishable, which means the notice must read the same in both cases.
 *
 * So it is a standing property of the surface, phrased in the present tense
 * about the view rather than about this pack's contents.
 */
export function PackCard({
  pack,
  all,
  documents,
  meetingTitle,
}: {
  pack: BoardPack;
  all: BoardPack[];
  documents: Document[];
  meetingTitle?: string;
}) {
  const replacement = supersededBy(pack, all);
  const rows = resolveItems(pack.items, documents);

  return (
    <Card className="p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3
            className={cn(
              "text-base font-semibold text-foreground",
              // A superseded pack is history, not the pre-read anyone should be
              // working from. Muting it is the cheapest honest signal.
              pack.superseded_by_id && "text-muted-foreground",
            )}
          >
            {pack.title}
          </h3>
          <p className="mt-1 text-xs text-subtle-foreground">
            {meetingTitle ?? pack.meeting_id} · Version {pack.version_no}
            {pack.published_at
              ? ` · Published ${formatDate(pack.published_at)}`
              : ` · Created ${formatDate(pack.created_at)}`}
          </p>
        </div>
        <Badge tone={PACK_STATUS_TONE[pack.status]}>{PACK_STATUS_LABEL[pack.status]}</Badge>
      </div>

      {/* Supersession is the version trail: which pre-read actually stood at the
          meeting. version_no is the published lineage, not the concurrency
          counter — see CONTRIBUTING.md on version vs version_no. */}
      {replacement && (
        <a
          href={`#${replacement.id}`}
          className="mt-3 inline-flex items-center gap-1.5 rounded-[6px] text-xs text-accent-emphasis hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised"
        >
          Replaced by version {replacement.version_no}
          <ArrowRight className="size-3" aria-hidden />
        </a>
      )}

      {rows.length > 0 ? (
        <ol className="mt-4 space-y-2 border-t border-border pt-4">
          {rows.map(({ item, document }) => (
            // Keyed by id, never by position: position is renumbered per caller,
            // so it is a label, not an identity.
            <li key={item.id} className="flex gap-3">
              <span
                className="mt-0.5 w-5 shrink-0 text-right text-xs tabular-nums text-subtle-foreground"
                aria-hidden
              >
                {item.position}
              </span>
              <FileText className="mt-0.5 size-3.5 shrink-0 text-subtle-foreground" aria-hidden />
              <div className="min-w-0 flex-1">
                {document ? (
                  <>
                    <p className="text-sm text-foreground">{document.title}</p>
                    <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-subtle-foreground">
                      <span>{DOC_TYPE_LABEL[document.doc_type]}</span>
                      <span aria-hidden>·</span>
                      <span>{SENSITIVITY_LABEL[document.sensitivity]}</span>
                    </p>
                  </>
                ) : (
                  // A reference that resolved to nothing. This is a dangling
                  // document_id, NOT a withheld document — withheld items never
                  // arrive. Saying "unavailable" here would invent a hidden
                  // record where there is only a broken link.
                  <p className="text-sm text-muted-foreground">
                    Document reference could not be resolved
                  </p>
                )}
                {item.note && (
                  <p className="mt-1.5 flex gap-1.5 text-xs text-muted-foreground">
                    <StickyNote className="mt-0.5 size-3 shrink-0" aria-hidden />
                    <span>{item.note}</span>
                  </p>
                )}
              </div>
            </li>
          ))}
        </ol>
      ) : (
        // Reads identically whether the pack is genuinely empty or every item in
        // it is above this caller's clearance. Those two states must not be
        // distinguishable.
        <p className="mt-4 border-t border-border pt-4 text-sm text-muted-foreground">
          No documents to show in this pack at your access level.
        </p>
      )}

      <p className="mt-4 flex items-center gap-1.5 text-xs text-subtle-foreground">
        <Lock className="size-3 shrink-0" aria-hidden />
        Pack contents are filtered to your access level. Some content may be unavailable.
      </p>
    </Card>
  );
}
