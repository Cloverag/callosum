"use client";

import { useEffect, useMemo, useState } from "react";
import { Gavel } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { LoadFailed, asApiError } from "@/components/ui/load-failed";
import type { ApiError } from "@/lib/http";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  DECISION_STATUSES,
  DECISION_STATUS_DOT,
  DECISION_STATUS_LABEL,
  decisionsApi,
  type Decision,
  type DecisionStatus,
} from "@/lib/decisions";
import { meetingsApi, type Meeting } from "@/lib/meetings";
import { DecisionCard } from "./decision-card";
import { StanceLegend } from "./stance-bar";

export default function DecisionsPage() {
  const [decisions, setDecisions] = useState<Decision[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [meetings, setMeetings] = useState<Meeting[] | null>(null);
  const [active, setActive] = useState<Set<DecisionStatus>>(new Set());

  useEffect(() => {
    // There is no workspace-wide decisions query — a decision exists only inside a
    // meeting, so the meetings must be fetched first and the decisions fanned out
    // across them. See the note on `decisionsApi`.
    meetingsApi
      .list()
      .then((ms) => {
        setMeetings(ms);
        return decisionsApi.listForMeetings(ms.map((m) => m.id));
      })
      .then(setDecisions)
      .catch((e) => setError(asApiError(e)));
  }, []);

  const meetingTitle = useMemo(() => {
    const byId = new Map((meetings ?? []).map((m) => [m.id, m.title]));
    return (id: string) => byId.get(id);
  }, [meetings]);

  // Counts come from the unfiltered set, so a filter chip never reports zero for
  // a status that exists — the count describes the data, not the current view.
  const counts = useMemo(() => {
    const c = new Map<DecisionStatus, number>();
    for (const d of decisions ?? []) c.set(d.status, (c.get(d.status) ?? 0) + 1);
    return c;
  }, [decisions]);

  const visible = useMemo(() => {
    if (!decisions) return null;
    return active.size === 0 ? decisions : decisions.filter((d) => active.has(d.status));
  }, [decisions, active]);

  function toggle(s: DecisionStatus) {
    setActive((prev) => {
      const next = new Set(prev);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return next;
    });
  }

  return (
    <div className="p-8">
      <PageHeader
        title="Decisions"
        description="What the board decided, who stood where, and what they said."
        icon={<Gavel />}
      />

      {/* Filters. Empty selection means "everything" rather than "nothing" — the
          more useful default, and it makes the cleared state a single click. */}
      <div className="mt-6 flex flex-wrap items-center gap-2">
        {DECISION_STATUSES.map((s) => {
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
              <span className={cn("size-1.5 rounded-full", DECISION_STATUS_DOT[s])} aria-hidden />
              {DECISION_STATUS_LABEL[s]}
              <span className="tabular-nums">{n}</span>
            </button>
          );
        })}
        {active.size > 0 && (
          <button
            type="button"
            onClick={() => setActive(new Set())}
            className="rounded-[6px] px-2 py-1 text-xs text-accent-emphasis hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          >
            Clear
          </button>
        )}
      </div>

      <div className="mt-4">
        <StanceLegend />
      </div>

      <div className="mt-6 space-y-4">
        {error ? (
          <LoadFailed what="Decisions" error={error} />
        ) : visible === null ? (
          Array.from({ length: 3 }).map((_, i) => (
            <Card key={i} className="p-6">
              <div className="h-4 w-2/5 rounded bg-surface-sunken" />
              <div className="mt-3 h-3 w-1/4 rounded bg-surface-sunken" />
              <div className="mt-5 h-2 w-full rounded-full bg-surface-sunken" />
            </Card>
          ))
        ) : visible.length === 0 ? (
          <Card className="p-10 text-center">
            <p className="text-sm text-muted-foreground">No decisions match these filters.</p>
          </Card>
        ) : (
          visible.map((d) => (
            // id anchors the supersession links between cards.
            <div key={d.id} id={d.id} className="scroll-mt-8">
              <DecisionCard decision={d} all={decisions ?? []} meetingTitle={meetingTitle(d.meeting_id)} />
            </div>
          ))
        )}
      </div>
    </div>
  );
}
