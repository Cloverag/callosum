"use client";

import * as React from "react";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { dayKey } from "@/lib/calendar";
import {
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

function todayInput(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

export function MeetingForm({
  open,
  editing,
  defaultDate,
  onClose,
}: {
  open: boolean;
  editing: Meeting | null;
  /** Pre-fills the date field when creating (e.g. the day the user pressed Enter on). */
  defaultDate?: Date | null;
  onClose: () => void;
  /** Accepted but unused until CP-D gives meetings write endpoints. */
  onSaved?: () => void;
}) {
  const [title, setTitle] = React.useState("");
  const [date, setDate] = React.useState("");
  const [start, setStart] = React.useState("09:00");
  const [end, setEnd] = React.useState("10:00");
  const [location, setLocation] = React.useState("");
  const [status, setStatus] = React.useState<MeetingStatus>("draft");
  const [saveError, setSaveError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!open) return;
    if (editing) {
      setTitle(editing.title);
      // A draft has no window until it is scheduled, so fall back to the defaults
      // rather than formatting a null into an Invalid Date.
      setDate(editing.scheduled_start ? toDateInput(editing.scheduled_start) : todayInput());
      setStart(editing.scheduled_start ? toTimeInput(editing.scheduled_start) : "09:00");
      setEnd(editing.scheduled_end ? toTimeInput(editing.scheduled_end) : "10:00");
      setLocation(editing.location ?? "");
      setStatus(editing.status);
    } else {
      setTitle("");
      setDate(dayKey(defaultDate ?? new Date()));
      setStart("09:00");
      setEnd("10:00");
      setLocation("");
      setStatus("draft");
    }
  }, [open, editing, defaultDate]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    // Writes are CP-D. There is no POST or PATCH endpoint yet, and the mock that
    // used to accept them is gone — so this says so rather than pretending to save
    // into somewhere that no longer exists. `onSaved` stays on the props for the
    // same reason: CP-D restores this path rather than rebuilding it.
    setSaveError("Creating and editing meetings is not available yet.");
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
          <Button type="submit" form="meeting-form" disabled>
            {editing ? "Save changes" : "Create meeting"}
          </Button>
        </>
      }
    >
      {saveError && (
        <p className="mb-3 rounded-[10px] bg-surface-sunken px-3 py-2 text-xs text-muted-foreground">
          {saveError}
        </p>
      )}

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
        </div>
      </form>
    </Dialog>
  );
}
