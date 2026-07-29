"use client";

import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { CalendarClock, MapPin, ArrowRight } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDayFull, formatTime, startOfDay } from "@/lib/calendar";
import { MEETING_STATUS_LABEL, MEETING_STATUS_TONE, isScheduled, type Meeting } from "@/lib/meetings";

/** "Today" / "Tomorrow" / "in 3 days" — the operator's first read on urgency. */
function relativeDay(start: Date): string {
  const days = Math.round((startOfDay(start).getTime() - startOfDay(new Date()).getTime()) / 86_400_000);
  if (days <= 0) return "Today";
  if (days === 1) return "Tomorrow";
  if (days < 7) return `in ${days} days`;
  if (days < 14) return "next week";
  return `in ${Math.round(days / 7)} weeks`;
}

/** A compact scannable fact in the hero's quick-stat strip. */
function Stat({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-lg bg-surface-sunken px-3 py-2">
      <div className="flex items-center gap-1.5 text-muted-foreground">
        <span className="[&_svg]:size-3.5" aria-hidden>{icon}</span>
        <span className="text-[10px] font-medium uppercase tracking-[0.08em]">{label}</span>
      </div>
      <div className="mt-1 truncate text-sm font-medium tabular-nums text-foreground">{value}</div>
    </div>
  );
}

export function MeetingHero({ meeting, loading }: { meeting: Meeting | null; loading: boolean }) {
  const router = useRouter();

  if (loading) {
    return (
      <Card variant="elevated" className="min-h-[16rem] border-border-strong p-7">
        <div className="h-3 w-32 rounded bg-surface-sunken" />
        <div className="mt-4 h-7 w-2/3 rounded bg-surface-sunken" />
        <div className="mt-4 h-5 w-1/2 rounded bg-surface-sunken" />
        <div className="mt-5 grid grid-cols-3 gap-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-12 rounded-lg bg-surface-sunken" />
          ))}
        </div>
        <div className="mt-6 flex gap-3">
          <div className="h-10 w-32 rounded-md bg-surface-sunken" />
          <div className="h-10 w-32 rounded-md bg-surface-sunken" />
        </div>
      </Card>
    );
  }

  // An unscheduled meeting has no date to headline, so it is treated like no
  // upcoming meeting rather than rendered with a fabricated one.
  if (!meeting || !isScheduled(meeting)) {
    return (
      <Card variant="elevated" className="flex min-h-[16rem] flex-col items-center justify-center border-border-strong p-7 text-center">
        <CalendarClock className="size-6 text-muted-foreground" aria-hidden />
        <h2 className="mt-3 text-sm font-medium text-foreground">No upcoming meetings</h2>
        <p className="mt-1 max-w-xs text-sm text-muted-foreground">
          Your next board meeting will appear here with its agenda and prep at a glance.
        </p>
        <Button variant="secondary" size="sm" className="mt-4" onClick={() => router.push("/calendar")}>
          Open calendar
        </Button>
      </Card>
    );
  }

  const start = new Date(meeting.scheduled_start);

  return (
    <Card variant="elevated" className="flex min-h-[16rem] flex-col border-border-strong p-7">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-subtle-foreground">
            Upcoming board meeting
          </span>
          <h2 className="mt-1.5 truncate text-xl font-medium tracking-tight text-foreground">{meeting.title}</h2>
        </div>
        <Badge tone={MEETING_STATUS_TONE[meeting.status]}>{MEETING_STATUS_LABEL[meeting.status]}</Badge>
      </div>

      {/* Prominent when */}
      <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-lg font-medium text-foreground">{relativeDay(start)}</span>
        <span className="text-sm tabular-nums text-muted-foreground">
          {formatDayFull(start)} · {formatTime(meeting.scheduled_start)} – {formatTime(meeting.scheduled_end)}
        </span>
      </div>

      {/* Quick stats */}
      {/* Agenda readiness and "Clearance Level N" used to sit here. Both came from
          fields the domain has never had: agenda is a separate aggregate, and a
          meeting carries no clearance — that is a property of a membership. A stat
          asserting something the system does not model is the same defect as a
          number nobody measured, so they are gone rather than approximated. */}
      <dl className="mt-4 grid grid-cols-1 gap-3">
        <Stat icon={<MapPin />} label="Location" value={meeting.location ?? "—"} />
      </dl>

      <div className="mt-auto flex flex-wrap items-center gap-3 pt-6">
        <Button size="md" className="px-6" onClick={() => router.push("/calendar")}>
          Prepare meeting
          <ArrowRight className="size-4" />
        </Button>
        <Button variant="secondary" size="md" onClick={() => router.push("/calendar")}>
          View agenda
        </Button>
      </div>
    </Card>
  );
}
