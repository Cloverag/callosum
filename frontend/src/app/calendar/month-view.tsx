import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { WEEKDAYS, monthGrid, isSameMonth, isToday, dayKey, formatDayFull } from "@/lib/calendar";
import type { Meeting } from "@/lib/meetings";
import { MeetingChip } from "./meeting-chip";
import { useDayGridKeys } from "./use-day-keys";

export function MonthView({
  cursor,
  byDay,
  active,
  onSelect,
  onNavigate,
  onActivate,
}: {
  cursor: Date;
  byDay: Map<string, Meeting[]>;
  active: Date;
  onSelect: (m: Meeting) => void;
  onNavigate: (next: Date) => void;
  onActivate: (day: Date) => void;
}) {
  const days = monthGrid(cursor);
  const { gridProps, cellProps } = useDayGridKeys({ active, columns: 7, onNavigate, onActivate });

  return (
    <Card className="mt-6 overflow-hidden">
      <div className="grid grid-cols-7 border-b border-border">
        {WEEKDAYS.map((d) => (
          <div
            key={d}
            className="px-2 py-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground"
          >
            {d}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-7" {...gridProps}>
        {days.map((day, i) => {
          const list = byDay.get(dayKey(day)) ?? [];
          const inMonth = isSameMonth(day, cursor);
          const today = isToday(day);
          const lastCol = i % 7 === 6;

          return (
            <div
              key={dayKey(day)}
              {...cellProps(day, list.length, formatDayFull(day))}
              className={cn(
                "min-h-28 border-b border-border p-1.5",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus",
                !lastCol && "border-r",
                !inMonth && "bg-surface"
              )}
            >
              <div className="flex justify-end">
                <span
                  className={cn(
                    "flex size-6 items-center justify-center rounded-full text-xs tabular-nums",
                    today
                      ? "bg-accent font-medium text-accent-foreground"
                      : inMonth
                        ? "text-foreground"
                        : "text-subtle-foreground"
                  )}
                >
                  {day.getDate()}
                </span>
              </div>
              <div className="mt-1 space-y-1">
                {list.slice(0, 3).map((m) => (
                  <MeetingChip key={m.id} meeting={m} onSelect={onSelect} />
                ))}
                {list.length > 3 && (
                  <div className="px-1.5 text-xs text-muted-foreground">+{list.length - 3} more</div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
