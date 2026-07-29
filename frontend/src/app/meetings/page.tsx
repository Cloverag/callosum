"use client";

import { useEffect, useMemo, useState } from "react";
import { Users } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  meetingsApi,
  scheduledOnly,
  MEETING_STATUS_LABEL,
  MEETING_STATUS_TONE,
  type Meeting,
} from "@/lib/meetings";
import { formatDayFull, formatTime, startOfDay } from "@/lib/calendar";

function Row({ m }: { m: Meeting }) {
  return (
    <div className="flex items-center gap-4 px-5 py-3">
      <div className="w-44 shrink-0">
        <div className="text-sm font-medium text-foreground">{m.scheduled_start ? formatDayFull(new Date(m.scheduled_start)) : "Not scheduled"}</div>
        <div className="text-xs tabular-nums text-muted-foreground">
          {m.scheduled_start && m.scheduled_end
            ? `${formatTime(m.scheduled_start)} – ${formatTime(m.scheduled_end)}`
            : "—"}
        </div>
      </div>
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm text-foreground">{m.title}</div>
        {m.location && <div className="truncate text-xs text-muted-foreground">{m.location}</div>}
      </div>
      <Badge tone={MEETING_STATUS_TONE[m.status]}>{MEETING_STATUS_LABEL[m.status]}</Badge>
    </div>
  );
}

function Section({ title, meetings }: { title: string; meetings: Meeting[] }) {
  return (
    <section>
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">
        {title} · {meetings.length}
      </h2>
      <Card className="overflow-hidden">
        {meetings.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-muted-foreground">No {title.toLowerCase()} meetings.</p>
        ) : (
          <div className="divide-y divide-border">
            {meetings.map((m) => (
              <Row key={m.id} m={m} />
            ))}
          </div>
        )}
      </Card>
    </section>
  );
}

export default function MeetingsPage() {
  const [meetings, setMeetings] = useState<Meeting[] | null>(null);

  useEffect(() => {
    meetingsApi.list().then(setMeetings);
  }, []);

  const { upcoming, past } = useMemo(() => {
    const now = startOfDay(new Date());
    const up: Meeting[] = [];
    const pa: Meeting[] = [];
    // Undated meetings are neither upcoming nor past — they are unscheduled, and
    // sorting them into either bucket would assert a date the record does not have.
    for (const m of scheduledOnly(meetings ?? [])) (new Date(m.scheduled_start) >= now ? up : pa).push(m);
    return { upcoming: up, past: pa.reverse() };
  }, [meetings]);

  return (
    <div className="p-6">
      <PageHeader title="Meetings" description="Every board meeting in the Acme Corp workspace." icon={<Users />} />
      <div className="mt-6 space-y-6">
        {meetings === null ? (
          <Card>
            <p className="px-5 py-8 text-center text-sm text-muted-foreground">Loading…</p>
          </Card>
        ) : (
          <>
            <Section title="Upcoming" meetings={upcoming} />
            <Section title="Past" meetings={past} />
          </>
        )}
      </div>
    </div>
  );
}
