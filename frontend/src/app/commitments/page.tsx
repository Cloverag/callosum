"use client";

import { useEffect, useMemo, useState } from "react";
import { ClipboardCheck } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  COMMITMENT_STATUSES,
  COMMITMENT_STATUS_DOT,
  COMMITMENT_STATUS_LABEL,
  commitmentsApi,
  isOpen,
  isOverdue,
  todayLocal,
  type Commitment,
  type CommitmentStatus,
} from "@/lib/commitments";
import { boardMembersApi, type BoardMember } from "@/lib/board-members";
import { CommitmentCard } from "./commitment-card";

/**
 * Commitments — what the board asked for, who owes it, and by when.
 *
 * "Today" is computed **once**, here, and passed down. `isOverdue` takes it as a
 * parameter for the same reason the Python does: a value that changes under the
 * caller makes a report irreproducible, and every card on this page must agree about
 * what day it is.
 *
 * The directory is fetched with `include_inactive: true` — a departed director may
 * still own historic work, and filtering them out would render those commitments as
 * ownerless rather than as inherited.
 */
export default function CommitmentsPage() {
  const [commitments, setCommitments] = useState<Commitment[] | null>(null);
  const [members, setMembers] = useState<BoardMember[]>([]);
  const [active, setActive] = useState<Set<CommitmentStatus>>(new Set());
  const [openOnly, setOpenOnly] = useState(false);

  // One value for the whole render, not one per card.
  const today = useMemo(() => todayLocal(), []);

  useEffect(() => {
    commitmentsApi.list().then(setCommitments);
    boardMembersApi.list({ include_inactive: true }).then(setMembers);
  }, []);

  // Counts describe the data, not the current view, so a chip never reports zero for
  // a status that exists.
  const counts = useMemo(() => {
    const c = new Map<CommitmentStatus, number>();
    for (const x of commitments ?? []) c.set(x.status, (c.get(x.status) ?? 0) + 1);
    return c;
  }, [commitments]);

  const overdueCount = useMemo(
    () => (commitments ?? []).filter((c) => isOverdue(c, today)).length,
    [commitments, today],
  );

  const visible = useMemo(() => {
    if (!commitments) return null;
    return commitments
      .filter((c) => (active.size === 0 ? true : active.has(c.status)))
      .filter((c) => (openOnly ? isOpen(c) : true));
  }, [commitments, active, openOnly]);

  function toggle(s: CommitmentStatus) {
    setActive((prev) => {
      const next = new Set(prev);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return next;
    });
  }

  const filtersActive = active.size > 0 || openOnly;

  return (
    <div className="p-8">
      <PageHeader
        title="Commitments"
        description="What the board asked for, who owes it, and by when."
        icon={<ClipboardCheck />}
      />

      <div className="mt-6 flex flex-wrap items-center gap-2">
        {/* "Outstanding" is the question a board actually asks, and no single status
            answers it — open, in progress and blocked are all still owed. */}
        <button
          type="button"
          onClick={() => setOpenOnly((v) => !v)}
          aria-pressed={openOnly}
          className={cn(
            "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs transition-colors",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface",
            openOnly
              ? "border-accent-border bg-accent-subtle text-accent-emphasis"
              : "border-border text-muted-foreground hover:border-border-strong hover:text-foreground",
          )}
        >
          Outstanding only
        </button>

        <span className="mx-1 h-4 w-px bg-border" aria-hidden />

        {COMMITMENT_STATUSES.map((s) => {
          const on = active.has(s);
          const n = counts.get(s) ?? 0;
          return (
            <button
              key={s}
              type="button"
              onClick={() => toggle(s)}
              aria-pressed={on}
              disabled={n === 0}
              className={cn(
                "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface",
                "disabled:cursor-not-allowed disabled:opacity-40",
                on
                  ? "border-accent-border bg-accent-subtle text-accent-emphasis"
                  : "border-border text-muted-foreground hover:border-border-strong hover:text-foreground",
              )}
            >
              <span className={cn("size-1.5 rounded-full", COMMITMENT_STATUS_DOT[s])} aria-hidden />
              {COMMITMENT_STATUS_LABEL[s]}
              <span className="tabular-nums">{n}</span>
            </button>
          );
        })}

        {filtersActive && (
          <button
            type="button"
            onClick={() => {
              setActive(new Set());
              setOpenOnly(false);
            }}
            className="rounded-[6px] px-2 py-1 text-xs text-accent-emphasis hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          >
            Clear
          </button>
        )}
      </div>

      {/* Counted from the same `today` every card uses, so the summary cannot
          disagree with the rows beneath it. */}
      {overdueCount > 0 && (
        <p className="mt-4 text-xs font-medium text-danger-emphasis">
          {overdueCount} outstanding {overdueCount === 1 ? "commitment is" : "commitments are"} past
          its due date.
        </p>
      )}

      <div className="mt-6 space-y-4">
        {visible === null ? (
          Array.from({ length: 3 }).map((_, i) => (
            <Card key={i} className="p-6">
              <div className="h-4 w-2/5 rounded bg-surface-sunken" />
              <div className="mt-3 h-3 w-1/4 rounded bg-surface-sunken" />
              <div className="mt-5 h-2 w-full rounded-full bg-surface-sunken" />
            </Card>
          ))
        ) : visible.length === 0 ? (
          <Card className="p-10 text-center">
            <p className="text-sm text-muted-foreground">No commitments match these filters.</p>
          </Card>
        ) : (
          visible.map((c) => (
            <div key={c.id} id={c.id} className="scroll-mt-8">
              <CommitmentCard commitment={c} members={members} today={today} />
            </div>
          ))
        )}
      </div>
    </div>
  );
}
