"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { LayoutDashboard, CalendarClock, ShieldAlert, ArrowRight } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { meetingsApi, MEETING_STATUS_LABEL, MEETING_STATUS_TONE, type Meeting } from "@/lib/meetings";
import { apiClient, type EntityConflict } from "@/lib/api";
import { formatDayFull, formatTime, startOfDay, startOfWeek, addDays } from "@/lib/calendar";

export default function DashboardPage() {
  const [meetings, setMeetings] = useState<Meeting[] | null>(null);
  const [conflicts, setConflicts] = useState<EntityConflict[] | null>(null);

  useEffect(() => {
    meetingsApi.list().then(setMeetings);
    apiClient.getPendingConflicts().then(setConflicts);
  }, []);

  const upcoming = useMemo(() => {
    const now = startOfDay(new Date());
    return (meetings ?? []).filter((m) => new Date(m.start) >= now);
  }, [meetings]);

  const thisWeek = useMemo(() => {
    const ws = startOfWeek(new Date());
    const we = addDays(ws, 7);
    return (meetings ?? []).filter((m) => {
      const d = new Date(m.start);
      return d >= ws && d < we;
    }).length;
  }, [meetings]);

  return (
    <div className="p-6">
      <PageHeader title="Dashboard" description="Board operations at a glance." icon={<LayoutDashboard />} />

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card className="overflow-hidden lg:col-span-2">
          <div className="flex items-center justify-between border-b border-border px-5 py-3">
            <h2 className="text-sm font-medium text-foreground">Upcoming meetings</h2>
            <Link
              href="/calendar"
              className="inline-flex items-center gap-1 rounded text-xs font-medium text-accent-emphasis hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
            >
              Open calendar <ArrowRight className="size-3.5" />
            </Link>
          </div>
          {meetings === null ? (
            <p className="px-5 py-8 text-center text-sm text-muted-foreground">Loading…</p>
          ) : upcoming.length === 0 ? (
            <p className="px-5 py-8 text-center text-sm text-muted-foreground">No upcoming meetings.</p>
          ) : (
            <div className="divide-y divide-border">
              {upcoming.slice(0, 5).map((m) => (
                <div key={m.id} className="flex items-center gap-4 px-5 py-3">
                  <div className="w-40 shrink-0">
                    <div className="text-sm font-medium text-foreground">{formatDayFull(new Date(m.start))}</div>
                    <div className="text-xs tabular-nums text-muted-foreground">{formatTime(m.start)}</div>
                  </div>
                  <div className="min-w-0 flex-1 truncate text-sm text-foreground">{m.title}</div>
                  <Badge tone={MEETING_STATUS_TONE[m.status]}>{MEETING_STATUS_LABEL[m.status]}</Badge>
                </div>
              ))}
            </div>
          )}
        </Card>

        <div className="space-y-6">
          <Card className="p-5">
            <div className="flex items-center gap-2 text-muted-foreground">
              <CalendarClock className="size-4" />
              <span className="text-xs font-medium uppercase tracking-[0.08em]">This week</span>
            </div>
            <div className="mt-2 text-2xl font-light tabular-nums text-foreground">
              {meetings === null ? "—" : thisWeek}
            </div>
            <p className="text-xs text-muted-foreground">meetings scheduled</p>
          </Card>

          <Link
            href="/entity-conflicts"
            className="block rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          >
            <Card className="p-5 transition-colors duration-150 hover:border-border-strong">
              <div className="flex items-center gap-2 text-muted-foreground">
                <ShieldAlert className="size-4" />
                <span className="text-xs font-medium uppercase tracking-[0.08em]">Pending reviews</span>
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl font-light tabular-nums text-foreground">
                  {conflicts === null ? "—" : conflicts.length}
                </span>
                {conflicts && conflicts.length > 0 && <Badge tone="warning">action needed</Badge>}
              </div>
              <p className="text-xs text-muted-foreground">entity conflicts to resolve</p>
            </Card>
          </Link>
        </div>
      </div>
    </div>
  );
}
