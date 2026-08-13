"use client";

import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { LayoutDashboard } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { LoadFailed, asApiError } from "@/components/ui/load-failed";
import type { ApiError } from "@/lib/http";
import type { StatSegment } from "@/components/ui/stat-bar";
import {
  meetingsApi,
  MEETING_STATUSES,
  MEETING_STATUS_DOT,
  MEETING_STATUS_LABEL,
  type Meeting,
  scheduledOnly,
} from "@/lib/meetings";
import { apiClient, type EntityConflict } from "@/lib/api";
import { insightsApi, type DashboardInsights } from "@/lib/insights";
import { decisionsApi, type Decision } from "@/lib/decisions";
import { addDays, startOfDay, startOfWeek } from "@/lib/calendar";
import { DailyBrief } from "./daily-brief";
import { MeetingHero } from "./meeting-hero";
import { InstitutionalMemoryBand } from "./institutional-memory-band";
import { BoardReadiness } from "./board-readiness";
import { NeedsYou, type ActionCounts } from "./needs-you";
import { MemoryHealth } from "./memory-health";
import { GraphQualityPanel } from "./graph-quality";
import { MemoryGrowth } from "./memory-growth";
import { RecentDecisions } from "./recent-decisions";
import { ApprovedFacts } from "./approved-facts";

export default function DashboardPage() {
  const [meetings, setMeetings] = useState<Meeting[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [conflicts, setConflicts] = useState<EntityConflict[] | null>(null);
  const [insights, setInsights] = useState<DashboardInsights | null>(null);
  const [decisions, setDecisions] = useState<Decision[] | null>(null);

  useEffect(() => {
    meetingsApi
      .list()
      .then((ms) => {
        setMeetings(ms);
        // Recent decisions need meetings first: the API has no workspace-wide list.
        return decisionsApi.listForMeetings(ms.map((m) => m.id));
      })
      .then((d) => setDecisions(d.slice(0, 5)))
      .catch((e) => setError(asApiError(e)));
    apiClient.getPendingConflicts().then(setConflicts);
    insightsApi.get().then(setInsights);
    // Newest five. The card links through to /decisions for the rest rather than
    // growing without bound on the dashboard.
  }, []);

  const upcoming = useMemo(() => {
    const now = startOfDay(new Date());
    // Unscheduled meetings have no date to compare, so they are not 'upcoming'.
    return scheduledOnly(meetings ?? []).filter((m) => new Date(m.scheduled_start) >= now);
  }, [meetings]);

  const nextMeeting = upcoming[0] ?? null;

  const counts: ActionCounts | null = useMemo(() => {
    if (!meetings || !conflicts || !insights) return null;
    return {
      decisions: decisions !== null ? decisions.filter((d) => d.status === "proposed").length : insights.pending.decisionsToSign,
      conflicts: conflicts.length,
      meetings: upcoming.filter((m) => m.status === "draft" || m.status === "scheduled").length,
      docs: insights.pending.docsToIngest,
    };
  }, [meetings, conflicts, insights, decisions, upcoming]);

  /**
   * The orientation line, assembled here rather than stored as prose.
   *
   * The counts used to be baked into `insights.dailyBrief` as a sentence — which
   * meant the page could greet you with "3 meetings this week" on a week with
   * none, and restated an approval-queue figure that was never measured. Every
   * number below is counted from the same mock data the cards render, so the
   * brief cannot contradict the page beneath it. Clauses with nothing to report
   * are dropped instead of printing a zero.
   */
  const brief: string | null = useMemo(() => {
    if (!meetings || !conflicts || !insights) return null;
    const weekStart = startOfWeek(new Date());
    const weekEnd = addDays(weekStart, 7);
    const thisWeek = scheduledOnly(meetings).filter((m) => {
      const start = new Date(m.scheduled_start);
      return start >= weekStart && start < weekEnd;
    }).length;

    const clauses: string[] = [];
    if (thisWeek > 0) clauses.push(`${thisWeek} meeting${thisWeek === 1 ? "" : "s"} this week`);
    if (conflicts.length > 0) {
      clauses.push(`${conflicts.length} name conflict${conflicts.length === 1 ? "" : "s"} awaiting your review`);
    }

    const lead = clauses.length ? `${clauses.join(" and ")}. ` : "";
    return `${lead}${insights.dailyBrief}`;
  }, [meetings, conflicts, insights]);

  const statusSegments: StatSegment[] = useMemo(() => {
    const byStatus = new Map<Meeting["status"], number>();
    for (const m of meetings ?? []) byStatus.set(m.status, (byStatus.get(m.status) ?? 0) + 1);
    return MEETING_STATUSES.filter((s) => (byStatus.get(s) ?? 0) > 0).map((s) => ({
      label: MEETING_STATUS_LABEL[s],
      value: byStatus.get(s)!,
      color: MEETING_STATUS_DOT[s],
    }));
  }, [meetings]);

  return (
    <div className="p-8">
      <PageHeader title="Dashboard" description="What needs you now, and whether the memory can be trusted." icon={<LayoutDashboard />} />

      {/* A failed load is stated once, at the top. Every card below already renders
          "—" for data it does not have, so the page degrades honestly underneath — but
          without this the reader would see a page of em dashes and conclude the
          workspace is empty rather than unreachable. */}
      {error && (
        <div className="mt-6">
          <LoadFailed what="Dashboard data" error={error} />
        </div>
      )}

      {/*
       * The entrance choreography — L4, `rules.md` §6 (2026-08-13).
       *
       * `--rise-index` is the band's place in the reading order, not a delay in
       * milliseconds: the page states the order it wants to be read in, and
       * `globals.css` owns what a beat is worth. Indices are contiguous and
       * ascend down the page, which is the only thing that makes the effect read
       * as one movement rather than four unrelated fades.
       *
       * It is deliberately on the three BANDS and not on their cards. Twelve
       * elements arriving one after another is a loading screen impersonating a
       * page; three is a page settling. The cards inside a band share their
       * band's beat, and `NeedsYou` keeps its own internal row stagger, which is
       * a list assembling rather than a second entrance.
       */}
      <div className="rise-in mt-6" style={{ "--rise-index": 0 } as CSSProperties}>
        <DailyBrief brief={brief} />
      </div>

      {/* Band A — operational: what needs me now.
          The hero spans the full width and the two supporting cards sit beneath
          it at equal weight. Previously all three shared a 2:1 split, which gave
          the next board meeting the same visual weight as a progress card and
          left the hero's own content cramped into two thirds. One focal surface,
          then its supports — hierarchy from size and position, not more colour. */}
      <div className="rise-in mt-8 flex flex-col gap-6" style={{ "--rise-index": 1 } as CSSProperties}>
        <MeetingHero meeting={nextMeeting} loading={meetings === null} />
        <div className="grid gap-6 lg:grid-cols-2">
          <NeedsYou counts={counts} />
          <BoardReadiness readiness={insights?.readiness ?? null} />
        </div>
      </div>

      {/* Band B — system health: can I trust the memory?
          Band separation is 40px (the `2xl` step). It was 48px, which is not a
          step on the scale DESIGN.md declares — the page was the only thing
          deciding how far apart its own bands sat.

          The section used to open with a 10px uppercase eyebrow — the quietest
          type in the system introducing half the page. It now opens on the
          second focal surface, which is what `--focal-memory` was declared for. */}
      <div className="rise-in mt-10" style={{ "--rise-index": 2 } as CSSProperties}>
        <InstitutionalMemoryBand memory={insights?.memory ?? null} />
        <div className="mt-6 flex flex-col gap-8">
          <MemoryHealth
            memory={insights?.memory ?? null}
            reviewVelocity={insights?.reviewVelocity ?? null}
            statusSegments={statusSegments}
          />
          <GraphQualityPanel quality={insights?.quality ?? null} />
          <MemoryGrowth growth={insights?.memoryGrowth ?? null} />
          <div className="grid gap-8 lg:grid-cols-2">
            <RecentDecisions decisions={decisions} />
            <ApprovedFacts facts={insights?.approvedFacts ?? null} />
          </div>
        </div>
      </div>
    </div>
  );
}
