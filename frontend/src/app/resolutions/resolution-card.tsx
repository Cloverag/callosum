"use client";

import { ArrowRight, Info, Scale } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  RESOLUTION_STATUS_LABEL,
  RESOLUTION_STATUS_TONE,
  VOTE_LABEL,
  VOTE_TONE,
  outcomeDivergesFromTally,
  supersededBy,
  type Resolution,
} from "@/lib/resolutions";
import { initialsOf, nameOf, type BoardMember } from "@/lib/board-members";
import { VoteBar } from "./vote-bar";

function formatDate(iso: string): string {
  // Pinned locale and zone: a browser-locale date differs between server and client
  // and produces a hydration mismatch. Same fix as the decisions, packs and minutes
  // cards.
  return new Date(iso).toLocaleDateString("en-US", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

/**
 * One resolution: the instrument, how the board voted, and who voted which way.
 *
 * Two things this card deliberately does NOT do:
 *
 * 1. It never presents the tally as the outcome. `status` is the outcome; the bar
 *    is how the room split. When the two disagree — which the domain allows, and
 *    which the seeded FY27 headcount resolution actually does — the card says so
 *    plainly rather than hiding the discrepancy or rendering something that looks
 *    like a bug.
 *
 * 2. It says nothing about signing, execution, or legal effect. `signing_state` is
 *    a single-value placeholder for P8 and is not surfaced at all, because a field
 *    on screen implies a fact behind it.
 */
export function ResolutionCard({
  resolution,
  all,
  members,
}: {
  resolution: Resolution;
  all: Resolution[];
  members: BoardMember[];
}) {
  const replacement = supersededBy(resolution, all);
  const diverges = outcomeDivergesFromTally(resolution);

  return (
    <Card className="p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3
            className={cn(
              "text-base font-semibold text-foreground",
              // A superseded instrument is history, not current policy.
              resolution.status === "superseded" && "text-muted-foreground",
            )}
          >
            {resolution.title}
          </h3>
          <p className="mt-1 text-xs text-subtle-foreground">
            Version {resolution.version_no}
            {resolution.adopted_at
              ? ` · Adopted ${formatDate(resolution.adopted_at)}`
              : ` · Drafted ${formatDate(resolution.created_at)}`}
          </p>
        </div>
        <Badge tone={RESOLUTION_STATUS_TONE[resolution.status]}>
          {RESOLUTION_STATUS_LABEL[resolution.status]}
        </Badge>
      </div>

      {/* The operative text, given room. A resolution is a document; truncating it
          behind a disclosure would make the card a summary of the thing rather
          than the thing. */}
      <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-foreground">
        {resolution.body}
      </p>

      {replacement && (
        <a
          href={`#${replacement.id}`}
          className="mt-3 inline-flex items-center gap-1.5 rounded-[6px] text-xs text-accent-emphasis hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised"
        >
          Amended by version {replacement.version_no}
          <ArrowRight className="size-3" aria-hidden />
        </a>
      )}

      <VoteBar resolution={resolution} className="mt-4" />

      {/* Stated, not hidden. A board can adopt against the arithmetic — a chair's
          casting vote, a weighted class, a rule this system was never told. Leaving
          the reader to spot the mismatch themselves is what makes a page feel
          untrustworthy. */}
      {diverges && (
        <p className="mt-3 flex gap-2 rounded-[10px] bg-surface-sunken px-3 py-2 text-xs text-muted-foreground">
          <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          <span>
            The recorded outcome differs from a simple majority of the votes shown.
            The outcome is what the board minuted; quorum and majority rules are not
            recorded in this system.
          </span>
        </p>
      )}

      {resolution.votes.length > 0 && (
        <ul className="mt-4 space-y-2 border-t border-border pt-4">
          {resolution.votes.map((v) => {
            const name = nameOf(v.board_member_id, members);
            return (
              <li key={v.id} className="flex items-center gap-3">
                <span
                  className="flex size-7 shrink-0 items-center justify-center rounded-full bg-surface-sunken text-[10px] font-semibold text-muted-foreground"
                  aria-hidden
                >
                  {name ? initialsOf(name) : "—"}
                </span>
                {/* An unresolved id renders as a plain reference, never as an
                    invented name. The directory is clearance-scoped, so a voter the
                    reader cannot resolve is a legitimate state. */}
                <span className="min-w-0 flex-1 truncate text-sm text-foreground">
                  {name ?? "Director not in the visible directory"}
                </span>
                <Badge tone={VOTE_TONE[v.vote]}>{VOTE_LABEL[v.vote]}</Badge>
              </li>
            );
          })}
        </ul>
      )}

      {resolution.status === "draft" && (
        <p className="mt-4 flex items-center gap-1.5 text-xs text-subtle-foreground">
          <Scale className="size-3 shrink-0" aria-hidden />
          Draft — open for votes, and still amendable.
        </p>
      )}
    </Card>
  );
}
