import { cn } from "@/lib/utils";
import { formatTime } from "@/lib/calendar";
import { MEETING_STATUS_DOT, MEETING_STATUS_LABEL, type Meeting } from "@/lib/meetings";

/** Compact clickable meeting row used inside month and week cells. */
export function MeetingChip({ meeting, onSelect }: { meeting: Meeting; onSelect: (m: Meeting) => void }) {
  return (
    <button
      onClick={() => onSelect(meeting)}
      title={`${formatTime(meeting.start)} · ${meeting.title} · ${MEETING_STATUS_LABEL[meeting.status]}`}
      className="flex w-full items-center gap-1.5 rounded px-1.5 py-1 text-left text-xs transition-colors duration-150 hover:bg-surface-elevated focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
    >
      <span className={cn("size-1.5 shrink-0 rounded-full", MEETING_STATUS_DOT[meeting.status])} aria-hidden />
      <span className="shrink-0 tabular-nums text-muted-foreground">{formatTime(meeting.start)}</span>
      <span className="truncate text-foreground">{meeting.title}</span>
    </button>
  );
}
