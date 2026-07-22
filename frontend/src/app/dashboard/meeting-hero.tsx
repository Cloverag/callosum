"use client";

import { useRouter } from "next/navigation";
import { CalendarClock, MapPin, ShieldCheck, ArrowRight } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDayFull, formatTime, startOfDay } from "@/lib/calendar";
import { MEETING_STATUS_LABEL, MEETING_STATUS_TONE, type Meeting } from "@/lib/meetings";

/** "Today" / "Tomorrow" / "in 3 days" — the operator's first read on urgency. */
function relativeDay(start: Date): string {
  const days = Math.round((startOfDay(start).getTime() - startOfDay(new Date()).getTime()) / 86_400_000);
  if (days <= 0) return "Today";
  if (days === 1) return "Tomorrow";
  if (days < 7) return `in ${days} days`;
  if (days < 14) return "next week";
  return `in ${Math.round(days / 7)} weeks`;
}

export function MeetingHero({ meeting, loading }: { meeting: Meeting | null; loading: boolean }) {
  const router = useRouter();

  if (loading) {
    return (
      <Card variant="elevated" className="min-h-[15rem] p-6">
        <div className="h-3 w-32 rounded bg-surface-raised" />
        <div className="mt-4 h-7 w-2/3 rounded bg-surface-raised" />
        <div className="mt-4 h-4 w-1/2 rounded bg-surface-raised" />
        <div className="mt-8 h-1.5 w-full rounded-full bg-surface-raised" />
        <div className="mt-6 flex gap-3">
          <div className="h-9 w-32 rounded-md bg-surface-raised" />
          <div className="h-9 w-32 rounded-md bg-surface-raised" />
        </div>
      </Card>
    );
  }

  if (!meeting) {
    return (
      <Card variant="elevated" className="flex min-h-[15rem] flex-col items-center justify-center p-6 text-center">
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

  const start = new Date(meeting.start);
  const end = new Date(meeting.end);
  const total = meeting.agenda.length;
  const withOwner = meeting.agenda.filter((a) => a.presenter).length;
  const readyPct = total === 0 ? 0 : Math.round((withOwner / total) * 100);

  return (
    <Card variant="elevated" className="flex min-h-[15rem] flex-col p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <span className="text-[10px] font-semibold uppercase tracking-[0.1em] text-accent-emphasis">
            Next board meeting
          </span>
          <h2 className="mt-1.5 truncate text-xl font-medium tracking-tight text-foreground">{meeting.title}</h2>
        </div>
        <Badge tone={MEETING_STATUS_TONE[meeting.status]}>{MEETING_STATUS_LABEL[meeting.status]}</Badge>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm text-muted-foreground">
        <span className="inline-flex items-center gap-1.5 font-medium text-foreground">
          <CalendarClock className="size-4 text-muted-foreground" aria-hidden />
          {relativeDay(start)}
        </span>
        <span className="tabular-nums">
          {formatDayFull(start)} · {formatTime(meeting.start)} – {formatTime(meeting.end)}
        </span>
        {meeting.location && (
          <span className="inline-flex items-center gap-1.5">
            <MapPin className="size-4" aria-hidden />
            {meeting.location}
          </span>
        )}
        <span className="inline-flex items-center gap-1.5">
          <ShieldCheck className="size-4" aria-hidden />
          Clearance L{meeting.sensitivity}
        </span>
      </div>

      {meeting.objectives && (
        <p className="mt-3 line-clamp-2 text-sm text-muted-foreground">{meeting.objectives}</p>
      )}

      <div className="mt-auto pt-6">
        <div className="flex items-center justify-between text-xs">
          <span className="font-medium text-foreground">Agenda readiness</span>
          <span className="tabular-nums text-muted-foreground">
            {total === 0 ? "No agenda yet" : `${withOwner} of ${total} items have an owner`}
          </span>
        </div>
        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-surface-sunken">
          <div className="h-full rounded-full bg-accent-emphasis transition-[width] duration-500" style={{ width: `${readyPct}%` }} />
        </div>

        <div className="mt-5 flex flex-wrap gap-3">
          <Button size="sm" onClick={() => router.push("/calendar")}>
            Open meeting
            <ArrowRight className="size-4" />
          </Button>
          <Button variant="secondary" size="sm" onClick={() => router.push("/calendar")}>
            Prepare agenda
          </Button>
        </div>
      </div>
    </Card>
  );
}
