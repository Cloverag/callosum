"use client";

import { useEffect, useMemo, useState } from "react";
import { ScrollText } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { LoadFailed, asApiError } from "@/components/ui/load-failed";
import type { ApiError } from "@/lib/http";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  MINUTES_STATUSES,
  MINUTES_STATUS_DOT,
  MINUTES_STATUS_LABEL,
  minutesApi,
  type Minutes,
  type MinutesStatus,
} from "@/lib/minutes";
import { meetingsApi, type Meeting } from "@/lib/meetings";

import { MinutesCard } from "./minutes-card";

/**
 * Minutes — the record of what each meeting resolved.
 *
 * Note what this page does not have: a clearance switch. `/packs` filters by the
 * caller's clearance server-side; `list_minutes` takes no clearance at all, so
 * offering any such control here would imply a filter that does not exist. The
 * absence is the honest mirror of the contract — see issue #49.
 *
 * The status chips filter in the browser, over minutes already returned. That is
 * presentation, not a query, and emphatically not a security filter.
 */
export default function MinutesPage() {
  const [minutes, setMinutes] = useState<Minutes[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [meetings, setMeetings] = useState<Meeting[] | null>(null);
  const [active, setActive] = useState<Set<MinutesStatus>>(new Set());

  useEffect(() => {
    let stale = false;
    // `MEETING_ID = "m-q3"` used to be hard-coded here — a mock identifier that no
    // real meeting has, so against the live API this page asked for minutes of a
    // meeting that does not exist and rendered nothing. `/packs` was fixed for this
    // in 9d11390 and this page was missed. Minutes belong to a meeting, so the
    // meetings are fetched first and every meeting's minutes are collected.
    meetingsApi
      .list()
      .then(async (ms) => {
        const perMeeting = await Promise.all(
          ms.map((m) => minutesApi.list({ meeting_id: m.id })),
        );
        if (stale) return;
        setMeetings(ms);
        setMinutes(perMeeting.flat());
      })
      // Deliberately NOT `.catch(() => setMinutes([]))`, which is what this was. That
      // renders "No minutes match these filters" — a confident statement about the
      // data — when the truth is that we do not know what the data is. A failed
      // request is not an empty result.
      .catch((e) => {
        if (stale) return;
        setError(asApiError(e));
      });
    return () => {
      stale = true;
    };
  }, []);

  const meetingTitle = useMemo(() => {
    const byId = new Map((meetings ?? []).map((m) => [m.id, m.title]));
    return (id: string) => byId.get(id);
  }, [meetings]);

  // Counts come from the unfiltered set, so a filter chip never reports zero for
  // a status that exists — the count describes the data, not the current view.
  const counts = useMemo(() => {
    const c = new Map<MinutesStatus, number>();
    for (const m of minutes ?? []) c.set(m.status, (c.get(m.status) ?? 0) + 1);
    return c;
  }, [minutes]);

  const visible = useMemo(() => {
    if (!minutes) return null;
    return active.size === 0 ? minutes : minutes.filter((m) => active.has(m.status));
  }, [minutes, active]);

  function toggle(s: MinutesStatus) {
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
        title="Minutes"
        description="What each meeting resolved, and every correction since."
        icon={<ScrollText />}
      />

      {/* Filters. Empty selection means "everything" rather than "nothing" — the
          more useful default, and it makes the cleared state a single click. */}
      <div className="mt-6 flex flex-wrap items-center gap-2">
        {MINUTES_STATUSES.map((s) => {
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
              <span className={cn("size-1.5 rounded-full", MINUTES_STATUS_DOT[s])} aria-hidden />
              {MINUTES_STATUS_LABEL[s]}
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
          <LoadFailed what="Minutes" error={error} />
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
            <p className="text-sm text-muted-foreground">No minutes match these filters.</p>
          </Card>
        ) : (
          visible.map((m) => (
            // id anchors the correction links between cards.
            <div key={m.id} id={m.id} className="scroll-mt-8">
              <MinutesCard
                minutes={m}
                all={minutes ?? []}
                meetingTitle={meetingTitle(m.meeting_id)}
              />
            </div>
          ))
        )}
      </div>
    </div>
  );
}
