import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { dayKey, formatDayFull, formatTime } from "@/lib/calendar";
import { MEETING_STATUS_LABEL, MEETING_STATUS_TONE, type Meeting } from "@/lib/meetings";

export function DayView({
  cursor,
  byDay,
  onSelect,
}: {
  cursor: Date;
  byDay: Map<string, Meeting[]>;
  onSelect: (m: Meeting) => void;
}) {
  const list = byDay.get(dayKey(cursor)) ?? [];

  return (
    <Card className="mt-6 overflow-hidden">
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
                className="flex w-full items-center gap-4 px-5 py-3 text-left transition-colors duration-150 hover:bg-surface-elevated focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus"
              >
                <span className="w-28 shrink-0 text-sm tabular-nums text-muted-foreground">
                  {formatTime(m.start)} – {formatTime(m.end)}
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
