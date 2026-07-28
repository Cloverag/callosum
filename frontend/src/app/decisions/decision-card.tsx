"use client";

import { ArrowRight, Quote } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  DECISION_STATUS_LABEL,
  DECISION_STATUS_TONE,
  STANCE_LABEL,
  STANCE_TONE,
  isTerminal,
  supersededBy,
  type Decision,
} from "@/lib/decisions";
import { StanceBar } from "./stance-bar";

function formatDate(iso: string): string {
  // Pinned locale and zone: a date rendered from the browser's locale differs
  // between server and client and produces a hydration mismatch. Same fix as
  // the entity-conflicts page.
  return new Date(iso).toLocaleDateString("en-US", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

/**
 * One decision, with how the board landed on it and what was actually said.
 *
 * The quotes are the point. A decision without its stances is a claim; a decision
 * showing who supported it, who objected, and in their own words is a record. That
 * distinction is the product, so the comments are given real space rather than
 * being folded behind a disclosure.
 */
export function DecisionCard({
  decision,
  all,
  meetingTitle,
}: {
  decision: Decision;
  all: Decision[];
  meetingTitle?: string;
}) {
  const replacement = supersededBy(decision, all);
  const withComments = decision.stances.filter((s) => s.comment);

  return (
    <Card className="p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3
            className={cn(
              "text-base font-semibold text-foreground",
              // A superseded decision is history, not current policy. Muting it is
              // the cheapest honest signal that the reader is looking at a record
              // rather than a live position.
              decision.status === "superseded" && "text-muted-foreground line-through decoration-1",
            )}
          >
            {decision.title}
          </h3>
          <p className="mt-1 text-xs text-subtle-foreground">
            {meetingTitle ?? decision.meeting_id} · {formatDate(decision.created_at)}
          </p>
        </div>
        <Badge tone={DECISION_STATUS_TONE[decision.status]}>
          {DECISION_STATUS_LABEL[decision.status]}
        </Badge>
      </div>

      {decision.rationale && (
        <p className="mt-3 text-sm text-muted-foreground">{decision.rationale}</p>
      )}

      {/* Supersession is the reversal trail — the thing a founder reconstructing a
          decision most needs and least often has. It gets a real affordance. */}
      {replacement && (
        <a
          href={`#${replacement.id}`}
          className="mt-3 inline-flex items-center gap-1.5 rounded-[6px] text-xs text-accent-emphasis hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised"
        >
          Replaced by “{replacement.title}”
          <ArrowRight className="size-3" aria-hidden />
        </a>
      )}

      <StanceBar decision={decision} className="mt-4" />

      {withComments.length > 0 && (
        <ul className="mt-4 space-y-3 border-t border-border pt-4">
          {withComments.map((s) => (
            <li key={s.id} className="flex gap-3">
              <Quote className="mt-0.5 size-3.5 shrink-0 text-subtle-foreground" aria-hidden />
              <div className="min-w-0">
                <p className="text-sm text-foreground">{s.comment}</p>
                <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-subtle-foreground">
                  {/* The recorded name, always — `person_name` is what was minuted and
                      is permanent audit data. `board_member_id` (CP5a) resolves it to
                      a directory entry where one exists, but it is nullable forever,
                      so the name is what renders and the link is the enhancement. */}
                  <span>{s.person_name}</span>
                  <Badge tone={STANCE_TONE[s.stance]}>{STANCE_LABEL[s.stance]}</Badge>
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}

      {!isTerminal(decision.status) && (
        <p className="mt-4 text-xs text-subtle-foreground">
          Open — can still be approved, rejected, or deferred.
        </p>
      )}
    </Card>
  );
}
