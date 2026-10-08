"use client";

import { ArrowRight, FileText, Lock, StickyNote } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FieldValue } from "@/components/ui/field-value";
import { withheld as withheldState } from "@/lib/field-state";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  PACK_STATUS_LABEL,
  PACK_STATUS_TONE,
  isEditable,
  PACK_LOCKED_MEETING_STATUSES,
  resolveItems,
  supersededBy,
  versionTrail,
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
 * WHY THE WITHHELD COUNT IS SHOWN (ADR-018, #198)
 * ---------------------------------------------------------------------------
 * This card used to carry an unconditional "some content may be unavailable" line, on
 * the reasoning that a conditional notice would itself disclose that something was
 * hidden. That reasoning predates ADR-018, which decided the opposite for views that
 * claim completeness: a pack claims to be the material for a meeting, so a director
 * must be told when it is not all of it. The API returns `withheld_items`; this card
 * renders it, as a count and nothing else, with the shared "N withheld" wording. Zero
 * renders nothing. The renumbering (no gap, no position) is unchanged: the count
 * replaces the covert channel rather than adding to it.
 */
export function PackCard({
  pack,
  all,
  documents,
  meetingTitle,
  meetingStatus,
  onEdit,
  onNewVersion,
}: {
  pack: BoardPack;
  all: BoardPack[];
  documents: Document[];
  meetingTitle?: string;
  /** Hints which controls to offer; the server enforces the same rule regardless. */
  meetingStatus?: string;
  onEdit?: () => void;
  onNewVersion?: () => void;
}) {
  const replacement = supersededBy(pack, all);
  const trail = versionTrail(pack, all);
  const canEdit = onEdit && isEditable(pack, meetingStatus);
  const canIssueNew =
    onNewVersion &&
    pack.status === "published" &&
    !pack.superseded_by_id &&
    meetingStatus !== undefined &&
    !PACK_LOCKED_MEETING_STATUSES.has(meetingStatus);
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
      {trail.length > 1 && (
        <nav aria-label="Versions of this pack" className="mt-3 flex flex-wrap items-center gap-1.5 text-xs">
          <span className="text-subtle-foreground">Versions</span>
          {trail.map((v) =>
            v.id === pack.id ? (
              <span
                key={v.id}
                aria-current="true"
                className="rounded-[6px] bg-surface-sunken px-2 py-0.5 text-foreground"
              >
                {v.version_no} · {PACK_STATUS_LABEL[v.status]}
              </span>
            ) : (
              <a
                key={v.id}
                href={`#${v.id}`}
                className="rounded-[6px] px-2 py-0.5 text-accent-emphasis hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
              >
                {v.version_no} · {PACK_STATUS_LABEL[v.status]}
              </a>
            ),
          )}
        </nav>
      )}

      {(canEdit || canIssueNew) && (
        <div className="mt-4 flex gap-2">
          {canEdit && (
            <Button variant="secondary" size="sm" onClick={onEdit}>
              Edit pack
            </Button>
          )}
          {canIssueNew && (
            <Button variant="secondary" size="sm" onClick={onNewVersion}>
              New version
            </Button>
          )}
        </div>
      )}

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
          No documents to show in this pack.
        </p>
      )}

      {pack.withheld_items > 0 && (
        // ADR-018: a pack claims to be the material for the meeting, so when the server
        // withheld some, say how many and that this is not everything. A COUNT only.
        <p className="mt-4 flex items-center gap-2 text-xs text-muted-foreground">
          <Lock className="size-3 shrink-0" aria-hidden />
          <FieldValue state={withheldState<number>(pack.withheld_items)} />
          <span>
            {pack.withheld_items === 1 ? "document is" : "documents are"} above your clearance.
            This pack is not everything the board holds for this meeting.
          </span>
        </p>
      )}
    </Card>
  );
}
