"use client";

import { AlertTriangle, CalendarClock, MessageSquare, Users } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  COMMITMENT_STATUS_LABEL,
  COMMITMENT_STATUS_TONE,
  isOverdue,
  isTerminal,
  type Commitment,
} from "@/lib/commitments";
import { initialsOf, nameOf, type BoardMember } from "@/lib/board-members";

function formatDay(day: string): string {
  // A bare YYYY-MM-DD parsed as a Date is UTC midnight, which renders as the previous
  // day west of Greenwich. Splitting the parts avoids the shift entirely — the same
  // class of bug `dayKey` in lib/calendar.ts exists to prevent.
  const [y, m, d] = day.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-US", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

function formatStamp(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

/**
 * One commitment, its owner, its deadline, and the trail of what happened to it.
 *
 * **Nothing about delivery is rendered.** `external_system`, `external_task_id`,
 * `delivery_status` and `delivery_attempts` are inert until P8 — every commitment is
 * `not_dispatched`, because no adapter exists. Showing a "Not dispatched" chip would
 * imply a dispatch feature the product does not have, which is the same reason
 * `signing_state` is absent from the resolutions card.
 *
 * The update trail is the substance. A status without the note that explains it is a
 * field; a status with its reasons is a record, and the backend enforces that by
 * making the note mandatory on every state change.
 */
export function CommitmentCard({
  commitment,
  members,
  today,
}: {
  commitment: Commitment;
  members: BoardMember[];
  /** The page decides what "today" is, once — see `isOverdue`. */
  today: string;
}) {
  const overdue = isOverdue(commitment, today);
  const ownerName = nameOf(commitment.owner_board_member_id, members);

  return (
    <Card className="p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3
            className={cn(
              "text-base font-semibold text-foreground",
              commitment.status === "cancelled" && "text-muted-foreground line-through decoration-1",
            )}
          >
            {commitment.title}
          </h3>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-subtle-foreground">
            <span className="inline-flex items-center gap-1.5">
              <span
                className="flex size-5 items-center justify-center rounded-full bg-surface-sunken text-[9px] font-semibold text-muted-foreground"
                aria-hidden
              >
                {ownerName ? initialsOf(ownerName) : "—"}
              </span>
              {/* An unresolved owner renders as a plain statement, never as an
                  invented name. The directory is clearance-scoped. */}
              {ownerName ?? "Owner not in the visible directory"}
            </span>
            {commitment.accountable_team && (
              <>
                <span aria-hidden>·</span>
                <span className="inline-flex items-center gap-1">
                  <Users className="size-3" aria-hidden />
                  {commitment.accountable_team}
                </span>
              </>
            )}
          </p>
        </div>
        <Badge tone={COMMITMENT_STATUS_TONE[commitment.status]}>
          {COMMITMENT_STATUS_LABEL[commitment.status]}
        </Badge>
      </div>

      {commitment.detail && (
        <p className="mt-3 text-sm text-muted-foreground">{commitment.detail}</p>
      )}

      <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        {commitment.due_date ? (
          <span
            className={cn(
              "inline-flex items-center gap-1.5",
              overdue ? "font-medium text-danger-emphasis" : "text-muted-foreground",
            )}
          >
            {overdue ? (
              <AlertTriangle className="size-3.5" aria-hidden />
            ) : (
              <CalendarClock className="size-3.5" aria-hidden />
            )}
            Due {formatDay(commitment.due_date)}
            {/* Only outstanding work can be overdue. Completed-late work is late in
                the record, not on the list of things still owed. */}
            {overdue && " — overdue"}
          </span>
        ) : (
          <span className="text-subtle-foreground">No deadline set</span>
        )}
        {commitment.completed_at && (
          <span className="text-muted-foreground">
            Completed {formatStamp(commitment.completed_at)}
          </span>
        )}
      </p>

      {commitment.updates.length > 0 && (
        <ol className="mt-4 space-y-3 border-t border-border pt-4">
          {commitment.updates.map((u) => {
            const author = nameOf(u.author_board_member_id, members);
            return (
              <li key={u.id} className="flex gap-3">
                <MessageSquare
                  className="mt-0.5 size-3.5 shrink-0 text-subtle-foreground"
                  aria-hidden
                />
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-foreground">{u.note}</p>
                  <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-subtle-foreground">
                    <span>{formatStamp(u.created_at)}</span>
                    {author && (
                      <>
                        <span aria-hidden>·</span>
                        <span>{author}</span>
                      </>
                    )}
                    {/* Only shown when this update actually moved the state. An
                        update that only reported progress carries new_status null. */}
                    {u.new_status && (
                      <Badge tone={COMMITMENT_STATUS_TONE[u.new_status]}>
                        {COMMITMENT_STATUS_LABEL[u.new_status]}
                      </Badge>
                    )}
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
      )}

      {commitment.status === "blocked" && (
        // Blocked is NOT terminal in the domain — blocked work is expected to resume.
        // Saying so keeps a reader from filing it with the cancelled work.
        <p className="mt-4 text-xs text-subtle-foreground">
          Blocked — still open, and can resume once the blocker clears.
        </p>
      )}
      {isTerminal(commitment.status) && (
        <p className="mt-4 text-xs text-subtle-foreground">
          Closed — this record is history and no longer editable.
        </p>
      )}
    </Card>
  );
}
