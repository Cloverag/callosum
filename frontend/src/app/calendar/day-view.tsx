import * as React from "react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { addDays, dayKey, formatDayFull, formatTime } from "@/lib/calendar";
import { MEETING_STATUS_LABEL, MEETING_STATUS_TONE, type ScheduledMeeting } from "@/lib/meetings";

export function DayView({
  cursor,
  byDay,
  onSelect,
  onNavigate,
}: {
  cursor: Date;
  byDay: Map<string, ScheduledMeeting[]>;
  onSelect: (m: ScheduledMeeting) => void;
  onNavigate: (next: Date) => void;
}) {
  const list = byDay.get(dayKey(cursor)) ?? [];

  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    // Only when the day region itself is focused — not a meeting row inside it.
    if (e.target !== e.currentTarget) return;
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      onNavigate(addDays(cursor, -1));
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      onNavigate(addDays(cursor, 1));
    }
  }

  return (
    <Card
      className="mt-6 overflow-hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus"
      tabIndex={0}
      role="group"
      aria-label={`Meetings on ${formatDayFull(cursor)} — use left and right arrows to change day`}
      onKeyDown={onKeyDown}
    >
      {list.length === 0 ? (
        <div className="px-5 py-16 text-center">
          <p className="text-sm text-muted-foreground">No meetings on {formatDayFull(cursor)}.</p>
        </div>
      ) : (
        <ul className="divide-y divide-border">
          {list.map((m) => (
            <li key={m.id}>
              <button
                onClick={() => onSelect(m)}
                className="flex w-full items-center gap-4 px-5 py-3 text-left transition-colors duration-(--duration-hover) hover:bg-surface-elevated focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus"
              >
                <span className="w-28 shrink-0 text-sm tabular-nums text-muted-foreground">
                  {formatTime(m.scheduled_start)} – {formatTime(m.scheduled_end)}
                </span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-sm font-medium text-foreground">{m.title}</span>
                  {m.location && <span className="truncate text-xs text-muted-foreground">{m.location}</span>}
                </span>
                <Badge tone={MEETING_STATUS_TONE[m.status]}>{MEETING_STATUS_LABEL[m.status]}</Badge>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
