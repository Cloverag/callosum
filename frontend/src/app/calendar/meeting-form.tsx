"use client";

import * as React from "react";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { dayKey } from "@/lib/calendar";
import {
  meetingsApi,
  MEETING_STATUSES,
  MEETING_STATUS_LABEL,
  type Meeting,
  type MeetingStatus,
} from "@/lib/meetings";

// Shared native-control styling, token-driven to match <Input>. color-scheme keeps
// the browser date/time pickers legible in both themes.
const field =
  "h-10 w-full rounded-md border border-border bg-surface-raised px-3 text-sm text-foreground " +
  "[color-scheme:light] dark:[color-scheme:dark] " +
  "focus-visible:outline-none focus-visible:border-accent focus-visible:ring-1 focus-visible:ring-focus " +
  "disabled:opacity-50";

const toDateInput = (iso: string) => dayKey(new Date(iso));
const toTimeInput = (iso: string) => {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
};

export function MeetingForm({
  open,
  editing,
  onClose,
  onSaved,
}: {
  open: boolean;
  editing: Meeting | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [title, setTitle] = React.useState("");
  const [date, setDate] = React.useState("");
  const [start, setStart] = React.useState("09:00");
  const [end, setEnd] = React.useState("10:00");
  const [location, setLocation] = React.useState("");
  const [status, setStatus] = React.useState<MeetingStatus>("draft");
  const [sensitivity, setSensitivity] = React.useState(2);
  const [objectives, setObjectives] = React.useState("");
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    if (!open) return;
    if (editing) {
      setTitle(editing.title);
      setDate(toDateInput(editing.start));
      setStart(toTimeInput(editing.start));
      setEnd(toTimeInput(editing.end));
      setLocation(editing.location ?? "");
      setStatus(editing.status);
      setSensitivity(editing.sensitivity);
      setObjectives(editing.objectives ?? "");
    } else {
      setTitle("");
      setDate(dayKey(new Date()));
      setStart("09:00");
      setEnd("10:00");
      setLocation("");
      setStatus("draft");
      setSensitivity(2);
      setObjectives("");
    }
  }, [open, editing]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    const payload = {
      title: title.trim(),
      status,
      start: `${date}T${start}:00`,
      end: `${date}T${end}:00`,
      location: location.trim() || undefined,
      objectives: objectives.trim() || undefined,
      sensitivity,
    };
    try {
      if (editing) await meetingsApi.update(editing.id, payload);
      else await meetingsApi.create(payload);
      onSaved();
      onClose();
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={editing ? "Edit meeting" : "New meeting"}
      footer={
        <>
          <Button variant="ghost" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="meeting-form" loading={saving}>
            {editing ? "Save changes" : "Create meeting"}
          </Button>
        </>
      }
    >
      <form id="meeting-form" onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-1.5">
          <label htmlFor="mtg-title" className="text-sm font-medium text-foreground">
            Title
          </label>
          <Input
            id="mtg-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            placeholder="Q3 Board Meeting"
          />
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div className="space-y-1.5">
            <label htmlFor="mtg-date" className="text-sm font-medium text-foreground">
              Date
            </label>
            <input id="mtg-date" type="date" required value={date} onChange={(e) => setDate(e.target.value)} className={field} />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="mtg-start" className="text-sm font-medium text-foreground">
              Start
            </label>
            <input id="mtg-start" type="time" required value={start} onChange={(e) => setStart(e.target.value)} className={field} />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="mtg-end" className="text-sm font-medium text-foreground">
              End
            </label>
            <input id="mtg-end" type="time" required value={end} onChange={(e) => setEnd(e.target.value)} className={field} />
          </div>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="mtg-loc" className="text-sm font-medium text-foreground">
            Location <span className="text-muted-foreground">(optional)</span>
          </label>
          <Input id="mtg-loc" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Zoom, HQ — Room A…" />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <label htmlFor="mtg-status" className="text-sm font-medium text-foreground">
              Status
            </label>
            <select
              id="mtg-status"
              value={status}
              onChange={(e) => setStatus(e.target.value as MeetingStatus)}
              className={field}
            >
              {MEETING_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {MEETING_STATUS_LABEL[s]}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <label htmlFor="mtg-clr" className="text-sm font-medium text-foreground">
              Clearance
            </label>
            <select
              id="mtg-clr"
              value={sensitivity}
              onChange={(e) => setSensitivity(Number(e.target.value))}
              className={field}
            >
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>
                  Level {n}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="mtg-obj" className="text-sm font-medium text-foreground">
            Objectives <span className="text-muted-foreground">(optional)</span>
          </label>
          <textarea
            id="mtg-obj"
            value={objectives}
            onChange={(e) => setObjectives(e.target.value)}
            rows={3}
            className="w-full resize-none rounded-md border border-border bg-surface-raised px-3 py-2 text-sm text-foreground focus-visible:border-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-focus"
          />
        </div>
      </form>
    </Dialog>
  );
}
