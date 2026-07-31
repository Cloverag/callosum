"use client";

import { useEffect, useMemo, useState } from "react";
import { Briefcase } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { LoadFailed, asApiError } from "@/components/ui/load-failed";
import type { ApiError } from "@/lib/http";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  PACK_STATUSES,
  PACK_STATUS_DOT,
  PACK_STATUS_LABEL,
  packsApi,
  type BoardPack,
  type PackStatus,
} from "@/lib/packs";
import { documentsApi, type Document } from "@/lib/documents";
import { meetingsApi, type Meeting } from "@/lib/meetings";
import { PackCard } from "./pack-card";

/**
 * Packs hang off a meeting, so this surface names one. A meeting picker is CP-F's
 * job; until then it is the demo board's meeting.
 */
const MEETING_ID = "m-q3";

/**
 * Board packs — the pre-read circulated before each meeting.
 *
 * **The clearance switch is gone, and its absence is the point.** It existed because
 * the mock had to be told which level to filter at. The real API resolves clearance
 * from the caller's active membership on every request (ADR-013) — there is nowhere
 * to pass one, and a client that could name its own would be able to ask for every
 * restricted document in the workspace.
 *
 * What it demonstrated still holds, it is simply no longer switchable from the
 * browser: `_fetch_items_for_packs` drops items above the caller's level before the
 * pack is serialised, then renumbers what survives.
 *
 * Note how this differs from `/memory`, deliberately. The graph surface tells you
 * *how many* nodes were withheld, because `graph_search` returns that count. This one
 * never does, because `list_packs` does not — and could not without undoing its own
 * renumbering. No gap appears in the numbering, no total changes, nothing announces
 * itself. That silence is the contract working, not a missing feature.
 */
type Loaded = { packs: BoardPack[]; documents: Document[] };

export default function PacksPage() {
  const [data, setData] = useState<Loaded | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [meetings, setMeetings] = useState<Meeting[] | null>(null);
  const [active, setActive] = useState<Set<PackStatus>>(new Set());

  useEffect(() => {
    let stale = false;
    // Pack items are filtered by the server at the caller's own clearance. The
    // Both are live as of CP-E. A title may still fail to resolve if an item points
    // at a document the caller may not read — the card renders that as an unresolved
    // reference, never as withheld content, which is the honest reading of a
    // dangling id.
    Promise.all([packsApi.list({ meeting_id: MEETING_ID }), documentsApi.list()])
      .then(([p, d]) => {
        if (stale) return;
        setData({ packs: p, documents: d });
      })
      .catch((e) => {
        if (stale) return;
        setError(asApiError(e));
      });
    return () => {
      stale = true;
    };
  }, []);

  const packs = data?.packs ?? null;
  const documents = data?.documents ?? [];

  useEffect(() => {
    meetingsApi.list().then(setMeetings).catch(() => setMeetings([]));
  }, []);

  const meetingTitle = useMemo(() => {
    const byId = new Map((meetings ?? []).map((m) => [m.id, m.title]));
    return (id: string) => byId.get(id);
  }, [meetings]);

  // Counts come from the unfiltered set, so a filter chip never reports zero for
  // a status that exists — the count describes the data, not the current view.
  // This counts PACKS, which every reader of the pack can already see; it is not
  // a count of items, which is the thing that must never be totalled.
  const counts = useMemo(() => {
    const c = new Map<PackStatus, number>();
    for (const p of packs ?? []) c.set(p.status, (c.get(p.status) ?? 0) + 1);
    return c;
  }, [packs]);

  const visible = useMemo(() => {
    if (!packs) return null;
    return active.size === 0 ? packs : packs.filter((p) => active.has(p.status));
  }, [packs, active]);

  function toggle(s: PackStatus) {
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
        title="Board packs"
        description="The pre-read circulated before each meeting, and which version stood."
        icon={<Briefcase />}
      />

      <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
        {/* Filters. Empty selection means "everything" rather than "nothing" — the
            more useful default, and it makes the cleared state a single click. */}
        <div className="flex flex-wrap items-center gap-2">
          {PACK_STATUSES.map((s) => {
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
                <span className={cn("size-1.5 rounded-full", PACK_STATUS_DOT[s])} aria-hidden />
                {PACK_STATUS_LABEL[s]}
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
      </div>

      <div className="mt-6 space-y-4">
        {error ? (
          <LoadFailed what="Board packs" error={error} />
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
            <p className="text-sm text-muted-foreground">No board packs match these filters.</p>
          </Card>
        ) : (
          visible.map((p) => (
            // id anchors the supersession links between cards.
            <div key={p.id} id={p.id} className="scroll-mt-8">
              <PackCard
                pack={p}
                all={packs ?? []}
                documents={documents}
                meetingTitle={meetingTitle(p.meeting_id)}
              />
            </div>
          ))
        )}
      </div>
    </div>
  );
}
