"use client";

import { useEffect, useMemo, useState } from "react";
import { LayoutDashboard } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import type { StatSegment } from "@/components/ui/stat-bar";
import {
  meetingsApi,
  MEETING_STATUSES,
  MEETING_STATUS_DOT,
  MEETING_STATUS_LABEL,
  type Meeting,
} from "@/lib/meetings";
import { apiClient, type EntityConflict } from "@/lib/api";
import { insightsApi, type DashboardInsights } from "@/lib/insights";
import { startOfDay } from "@/lib/calendar";
import { MeetingHero } from "./meeting-hero";
import { NeedsYou, type ActionCounts } from "./needs-you";
import { MemoryHealth } from "./memory-health";
import { ApprovedFacts } from "./approved-facts";

export default function DashboardPage() {
  const [meetings, setMeetings] = useState<Meeting[] | null>(null);
  const [conflicts, setConflicts] = useState<EntityConflict[] | null>(null);
  const [insights, setInsights] = useState<DashboardInsights | null>(null);

  useEffect(() => {
    meetingsApi.list().then(setMeetings);
    apiClient.getPendingConflicts().then(setConflicts);
    insightsApi.get().then(setInsights);
  }, []);

  const upcoming = useMemo(() => {
    const now = startOfDay(new Date());
    return (meetings ?? []).filter((m) => new Date(m.start) >= now);
  }, [meetings]);

  const nextMeeting = upcoming[0] ?? null;

  const counts: ActionCounts | null = useMemo(() => {
    if (!meetings || !conflicts || !insights) return null;
    return {
      decisions: insights.pending.decisionsToSign,
      conflicts: conflicts.length,
      meetings: upcoming.filter((m) => m.status === "draft" || m.status === "scheduled").length,
      docs: insights.pending.docsToIngest,
    };
  }, [meetings, conflicts, insights, upcoming]);

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
    <div className="p-6">
      <PageHeader title="Dashboard" description="What needs you now, and whether the memory can be trusted." icon={<LayoutDashboard />} />

      {/* Band A — operational: what needs me now */}
      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <MeetingHero meeting={nextMeeting} loading={meetings === null} />
        </div>
        <NeedsYou counts={counts} />
      </div>

      {/* Band B — system health: can I trust the memory? */}
      <div className="mt-10">
        <h2 className="text-[10px] font-semibold uppercase tracking-[0.1em] text-subtle-foreground">Institutional memory</h2>
        <div className="mt-3 grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <MemoryHealth
              memory={insights?.memory ?? null}
              reviewVelocity={insights?.reviewVelocity ?? null}
              statusSegments={statusSegments}
            />
          </div>
          <ApprovedFacts facts={insights?.approvedFacts ?? null} />
        </div>
      </div>
    </div>
  );
}
