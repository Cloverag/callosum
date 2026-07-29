"use client";

import { useEffect, useMemo, useState } from "react";
import { Scale } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  RESOLUTION_STATUSES,
  RESOLUTION_STATUS_DOT,
  RESOLUTION_STATUS_LABEL,
  resolutionsApi,
  type Resolution,
  type ResolutionStatus,
} from "@/lib/resolutions";
import { boardMembersApi, type BoardMember } from "@/lib/board-members";
import { ApiError } from "@/lib/http";
import { ResolutionCard } from "./resolution-card";

/**
 * Resolutions — the formal instruments the board passed, and how it voted.
 *
 * The directory is fetched with `active: "all"`, which looks wrong and is
 * not: a director who has since left still cast the votes on record. Fetching only
 * active members would make historic votes render as unresolvable, which reads as
 * data loss rather than as a departure.
 */
export default function ResolutionsPage() {
  const [resolutions, setResolutions] = useState<Resolution[] | null>(null);
  const [members, setMembers] = useState<BoardMember[]>([]);
  const [active, setActive] = useState<Set<ResolutionStatus>>(new Set());
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    // A real request can fail; the mock this replaced never could. Without a catch
    // the page would sit on its loading skeleton forever and log an unhandled
    // rejection, which reads as "still loading" rather than "something went wrong".
    //
    // Deliberately NOT `.catch(() => setResolutions([]))`. That renders "no
    // resolutions match these filters" — a statement about the data — when the truth
    // is that we do not know what the data is. Showing an empty state for a failed
    // request is the same class of error as printing an unmeasured number.
    resolutionsApi
      .list()
      .then(setResolutions)
      .catch((err: unknown) => setError(err instanceof ApiError ? err : new ApiError(0, "network", "Could not reach the server.")));
    boardMembersApi.list({ active: "all" }).then(setMembers).catch(() => setMembers([]));
  }, []);

  // Counts come from the unfiltered set, so a chip never reports zero for a status
  // that exists — the count describes the data, not the current view.
  const counts = useMemo(() => {
    const c = new Map<ResolutionStatus, number>();
    for (const r of resolutions ?? []) c.set(r.status, (c.get(r.status) ?? 0) + 1);
    return c;
  }, [resolutions]);

  const visible = useMemo(() => {
    if (!resolutions) return null;
    return active.size === 0 ? resolutions : resolutions.filter((r) => active.has(r.status));
  }, [resolutions, active]);

  function toggle(s: ResolutionStatus) {
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
        title="Resolutions"
        description="The formal instruments the board passed, and how each director voted."
        icon={<Scale />}
      />

      {/* Filters. Empty selection means "everything" rather than "nothing" — the
          more useful default, and it makes the cleared state a single click. */}
      <div className="mt-6 flex flex-wrap items-center gap-2">
        {RESOLUTION_STATUSES.map((s) => {
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
              <span className={cn("size-1.5 rounded-full", RESOLUTION_STATUS_DOT[s])} aria-hidden />
              {RESOLUTION_STATUS_LABEL[s]}
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

      <div className="mt-6 space-y-4">
        {error ? (
          <Card className="p-10 text-center">
            <p className="text-sm text-foreground">Resolutions could not be loaded.</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {error.needsWorkspace
                ? "Select a workspace to continue."
                : error.isUnauthenticated
                  ? "Your session has ended. Sign in again."
                  : error.message}
            </p>
          </Card>
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
            <p className="text-sm text-muted-foreground">No resolutions match these filters.</p>
          </Card>
        ) : (
          visible.map((r) => (
            // id anchors the amendment links between cards.
            <div key={r.id} id={r.id} className="scroll-mt-8">
              <ResolutionCard resolution={r} all={resolutions ?? []} members={members} />
            </div>
          ))
        )}
      </div>
    </div>
  );
}
