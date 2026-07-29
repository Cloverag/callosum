import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { WEEKDAYS, weekDays, isToday, dayKey, formatDayFull } from "@/lib/calendar";
import type { ScheduledMeeting } from "@/lib/meetings";
import { MeetingChip } from "./meeting-chip";
import { useDayGridKeys } from "./use-day-keys";

export function WeekView({
  cursor,
  byDay,
  active,
  onSelect,
  onNavigate,
  onActivate,
}: {
  cursor: Date;
  byDay: Map<string, ScheduledMeeting[]>;
  active: Date;
  onSelect: (m: ScheduledMeeting) => void;
  onNavigate: (next: Date) => void;
  onActivate: (day: Date) => void;
}) {
  const days = weekDays(cursor);
  const { gridProps, cellProps } = useDayGridKeys({ active, columns: 7, onNavigate, onActivate });

  return (
    <Card className="mt-6 overflow-hidden">
      <div className="grid grid-cols-7 divide-x divide-border" {...gridProps}>
        {days.map((day, i) => {
          const list = byDay.get(dayKey(day)) ?? [];
          const today = isToday(day);

          return (
            <div
              key={dayKey(day)}
              {...cellProps(day, list.length, formatDayFull(day))}
              className="min-h-[30rem] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus"
            >
              <div className="border-b border-border px-2 py-2 text-center">
                <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                  {WEEKDAYS[i]}
                </div>
                <div
                  className={cn(
                    "mx-auto mt-1 flex size-7 items-center justify-center rounded-full text-sm tabular-nums",
                    today ? "bg-accent font-medium text-accent-foreground" : "text-foreground"
                  )}
                >
                  {day.getDate()}
                </div>
              </div>
              <div className="space-y-1 p-1.5">
                {list.map((m) => (
                  <MeetingChip key={m.id} meeting={m} onSelect={onSelect} />
                ))}
                {list.length === 0 && (
                  <p className="px-1.5 py-2 text-center text-xs text-subtle-foreground">—</p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
