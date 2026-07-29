"use client";

import { useEffect, useState } from "react";
import { Clock, MapPin, Pencil } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { agendaApi, type AgendaItem } from "@/lib/agenda";
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
  // Agenda is its own aggregate (CP2), so it is fetched rather than read off the
  // meeting. `null` means "not loaded yet" and renders as loading; an empty array
  // means the meeting genuinely has no items. Conflating the two would show "no
  // agenda items yet" while the request was still in flight.
  const [loaded, setLoaded] = useState<{ meetingId: string; items: AgendaItem[] } | null>(null);

  useEffect(() => {
    if (!meeting) return;
    let stale = false;
    agendaApi
      .list(meeting.id)
      .then((items) => !stale && setLoaded({ meetingId: meeting.id, items }))
      // An agenda that cannot be loaded shows as empty rather than blocking the rest
      // of the dialog, which still carries the meeting's own details.
      .catch(() => !stale && setLoaded({ meetingId: meeting.id, items: [] }));
    return () => {
      stale = true;
    };
  }, [meeting]);

  // Which meeting the loaded agenda belongs to is checked during render rather than
  // cleared in the effect. That avoids a cascading render, and — the reason that
  // matters — it makes it impossible to paint one meeting's agenda under another's
  // title while a new fetch is in flight.
  const agenda = loaded && meeting && loaded.meetingId === meeting.id ? loaded.items : null;

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
          </dl>

          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">Agenda</h3>
            {agenda === null ? (
              <p className="text-muted-foreground">Loading agenda…</p>
            ) : agenda.length === 0 ? (
              <p className="text-muted-foreground">No agenda items yet.</p>
            ) : (
              <ol className="space-y-1.5">
                {agenda.map((item) => (
                  <li
                    key={item.id}
                    className="flex items-baseline justify-between gap-3 rounded-md border border-border bg-surface-elevated px-3 py-2"
                  >
                    <span className="flex items-baseline gap-2">
                      <span className="tabular-nums text-xs text-muted-foreground">{item.position}.</span>
                      <span className="text-foreground">{item.title}</span>
                    </span>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {item.duration_minutes === null ? "untimed" : `${item.duration_minutes}m`}
                      {item.presenter ? ` · ${item.presenter}` : ""}
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
