"use client";

import { Clock, MapPin, ShieldCheck, Pencil } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDayFull, formatTime } from "@/lib/calendar";
import { MEETING_STATUS_LABEL, MEETING_STATUS_TONE, type Meeting } from "@/lib/meetings";

export function MeetingDetail({
  meeting,
  onClose,
  onEdit,
}: {
  meeting: Meeting | null;
  onClose: () => void;
  onEdit: (m: Meeting) => void;
}) {
  return (
    <Dialog
      open={!!meeting}
      onClose={onClose}
      title={meeting?.title ?? ""}
      description={
        meeting ? (
          <span className="flex items-center gap-2">
            <Badge tone={MEETING_STATUS_TONE[meeting.status]}>{MEETING_STATUS_LABEL[meeting.status]}</Badge>
            <span>{formatDayFull(new Date(meeting.start))}</span>
          </span>
        ) : undefined
      }
      footer={
        meeting ? (
          <>
            <Button variant="ghost" onClick={onClose}>
              Close
            </Button>
            <Button variant="secondary" onClick={() => onEdit(meeting)}>
              <Pencil className="size-4" />
              Edit
            </Button>
          </>
        ) : undefined
      }
    >
      {meeting && (
        <div className="space-y-4 text-sm">
          <dl className="grid grid-cols-[auto_1fr] items-center gap-x-3 gap-y-2">
            <dt className="flex items-center gap-1.5 text-muted-foreground">
              <Clock className="size-4" />
              Time
            </dt>
            <dd className="text-foreground">
              {formatTime(meeting.start)} – {formatTime(meeting.end)}
            </dd>
            {meeting.location && (
              <>
                <dt className="flex items-center gap-1.5 text-muted-foreground">
                  <MapPin className="size-4" />
                  Location
                </dt>
                <dd className="text-foreground">{meeting.location}</dd>
              </>
            )}
            <dt className="flex items-center gap-1.5 text-muted-foreground">
              <ShieldCheck className="size-4" />
              Clearance
            </dt>
            <dd className="text-foreground">Level {meeting.sensitivity}</dd>
          </dl>

          {meeting.objectives && <p className="text-muted-foreground">{meeting.objectives}</p>}

          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">Agenda</h3>
            {meeting.agenda.length === 0 ? (
              <p className="text-muted-foreground">No agenda items yet.</p>
            ) : (
              <ol className="space-y-1.5">
                {meeting.agenda.map((item) => (
                  <li
                    key={item.id}
                    className="flex items-baseline justify-between gap-3 rounded-md border border-border bg-surface-elevated px-3 py-2"
                  >
                    <span className="flex items-baseline gap-2">
                      <span className="tabular-nums text-xs text-muted-foreground">{item.order}.</span>
                      <span className="text-foreground">{item.title}</span>
                    </span>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {item.timeboxMins}m{item.presenter ? ` · ${item.presenter}` : ""}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </div>
      )}
    </Dialog>
  );
}
