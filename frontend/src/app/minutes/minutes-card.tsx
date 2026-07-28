"use client";

import { ArrowRight, ScrollText } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  MINUTES_STATUS_LABEL,
  MINUTES_STATUS_TONE,
  supersededBy,
  type Minutes,
} from "@/lib/minutes";

function formatDate(iso: string): string {
  // Pinned locale and zone: a date rendered from the browser's locale differs
  // between server and client and produces a hydration mismatch. Same fix as
  // the decisions, packs and entity-conflicts pages.
  return new Date(iso).toLocaleDateString("en-US", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

/**
 * One minutes record.
 *
 * The body is rendered as paragraphs and nothing more. `minutes.body` is
 * unstructured TEXT with no schema behind it (`0010_board_pack`), so parsing it
 * for headings, attendees or action items would be reading a format into free
 * prose that the backend has never promised — and would silently drop content
 * the moment a record didn't match the assumed shape.
 *
 * There is no access-level notice here, unlike the board-pack card. Minutes are
 * not clearance-filtered; saying they were would imply a boundary the product
 * does not currently enforce.
 */
export function MinutesCard({
  minutes,
  all,
  meetingTitle,
}: {
  minutes: Minutes;
  all: Minutes[];
  meetingTitle?: string;
}) {
  const replacement = supersededBy(minutes, all);
  const paragraphs = minutes.body.split("\n").filter((line) => line.trim().length > 0);

  return (
    <Card className="p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3
            className={cn(
              "text-base font-semibold text-foreground",
              // A superseded record is history, not the standing minutes.
              minutes.superseded_by_id && "text-muted-foreground",
            )}
          >
            {meetingTitle ?? minutes.meeting_id}
          </h3>
          <p className="mt-1 text-xs text-subtle-foreground">
            Version {minutes.version_no}
            {minutes.finalised_at
              ? ` · Finalised ${formatDate(minutes.finalised_at)}`
              : ` · Drafted ${formatDate(minutes.created_at)}`}
          </p>
        </div>
        <Badge tone={MINUTES_STATUS_TONE[minutes.status]}>
          {MINUTES_STATUS_LABEL[minutes.status]}
        </Badge>
      </div>

      {/* The correction trail. A superseded set of minutes is the most
          consequential thing this surface can show: it is the record of the
          record changing, which is exactly what a board needs to be able to
          reconstruct and what usually goes missing. */}
      {replacement && (
        <a
          href={`#${replacement.id}`}
          className="mt-3 inline-flex items-center gap-1.5 rounded-[6px] text-xs text-accent-emphasis hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised"
        >
          Corrected by version {replacement.version_no}
          <ArrowRight className="size-3" aria-hidden />
        </a>
      )}

      <div className="mt-4 flex gap-3 border-t border-border pt-4">
        <ScrollText className="mt-0.5 size-3.5 shrink-0 text-subtle-foreground" aria-hidden />
        <div className="min-w-0 space-y-3">
          {paragraphs.map((para, i) => (
            // Index keys are safe here and only here: paragraphs are derived from
            // an immutable body string, never reordered, never independently
            // addressable. Everywhere a record has an id, the id is the key.
            <p key={i} className="text-sm text-foreground">
              {para}
            </p>
          ))}
        </div>
      </div>

      {minutes.status === "draft" && (
        <p className="mt-4 text-xs text-subtle-foreground">
          Draft — not yet finalised, and still editable.
        </p>
      )}
    </Card>
  );
}
