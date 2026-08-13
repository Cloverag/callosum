"use client";

import * as React from "react";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/vendor/select";
import { dayKey } from "@/lib/calendar";
import {
  MEETING_STATUSES,
  MEETING_STATUS_LABEL,
  changesBetween,
  meetingsApi,
  type Meeting,
  type MeetingStatus,
} from "@/lib/meetings";
import { ApiError } from "@/lib/http";

/**
 * A conflict the user has to decide about, not an error to dismiss.
 *
 * `theirs` is the server's current copy, fetched *after* the 409 — so the dialog can
 * show what actually changed rather than telling the user something went wrong and
 * leaving them to find out what.
 */
type Conflict = {
  theirs: Meeting;
  expected: number;
  current: number;
};

// Shared native-control styling, token-driven to match <Input>. color-scheme keeps
// the browser date/time pickers legible in both themes.
// Radius and focus ring match `ui/input.tsx` deliberately: these native
// date/time controls sit in the same form as an <Input>, and at `rounded-md`
// they gave that one form two different corner radii. Meridian's control
// radius is 12px (DESIGN.md — Radius).
const field =
  "h-10 w-full rounded-[12px] border border-border bg-surface-raised px-3 text-sm text-foreground " +
  "transition-colors duration-(--duration-hover) " +
  "focus-visible:outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-focus/40 " +
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
  onSaved,
}: {
  open: boolean;
  editing: Meeting | null;
  /** Pre-fills the date field when creating (e.g. the day the user pressed Enter on). */
  defaultDate?: Date | null;
  onClose: () => void;
  /** Called after a successful create, update or transition, so the caller can refetch. */
  onSaved?: () => void;
}) {
  const [title, setTitle] = React.useState("");
  const [date, setDate] = React.useState("");
  const [start, setStart] = React.useState("09:00");
  const [end, setEnd] = React.useState("10:00");
  const [location, setLocation] = React.useState("");
  const [status, setStatus] = React.useState<MeetingStatus>("draft");
  const [saveError, setSaveError] = React.useState<string | null>(null);
  const [conflict, setConflict] = React.useState<Conflict | null>(null);
  const [saving, setSaving] = React.useState(false);

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
    setSaveError(null);
    setConflict(null);
  }, [open, editing, defaultDate]);

  /** Local date + time inputs to the ISO instant the API stores. */
  function isoAt(time: string): string {
    return new Date(`${date}T${time}`).toISOString();
  }

  /**
   * Saves against a known version.
   *
   * Split out from the submit handler so "save mine anyway" can re-run it against the
   * server's current version without duplicating any of the request building — a
   * second copy is how the retry path ends up sending a subtly different body.
   */
  async function save(againstVersion: number | null) {
    setSaving(true);
    setSaveError(null);
    try {
      if (!editing || againstVersion === null) {
        await meetingsApi.create({
          title,
          scheduled_start: isoAt(start),
          scheduled_end: isoAt(end),
          location: location.trim() === "" ? null : location,
        });
      } else {
        // Only what changed. Sending the whole form would clear every field the user
        // left empty, because the API reads `null` as "clear this".
        const changes = changesBetween(editing, {
          title,
          scheduled_start: isoAt(start),
          scheduled_end: isoAt(end),
          location: location.trim() === "" ? null : location,
        });
        let current = editing;
        if (Object.keys(changes).length > 0) {
          current = await meetingsApi.update(editing.id, againstVersion, changes);
        }
        // Status is deliberately not patchable — it moves through the state machine,
        // so it is a second call and only when it actually changed.
        if (status !== editing.status) {
          await meetingsApi.transition(editing.id, status, current.version);
        }
      }
      setConflict(null);
      onSaved?.();
      onClose();
    } catch (error) {
      await handleSaveError(error);
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveError(error: unknown) {
    if (!(error instanceof ApiError)) {
      setSaveError("Something went wrong saving this meeting.");
      return;
    }

    // A stale version is the one conflict a user can actually resolve, so it gets a
    // decision rather than a message. Fetch what is actually there now — showing the
    // other version without showing what it says would be an error dressed as help.
    if (error.isStale && editing) {
      const theirs = await meetingsApi.get(editing.id);
      const versions = error.versions;
      if (theirs && versions) {
        setConflict({ theirs, expected: versions.expected, current: versions.current });
        return;
      }
      setSaveError("This meeting changed while you were editing it. Reopen it to see the current version.");
      return;
    }

    // Everything else 409 refuses the operation itself — a completed meeting, an
    // illegal move. Retrying cannot help, so nothing here offers to.
    if (error.isUnretryableConflict) {
      setSaveError(error.message);
      return;
    }

    // 422 and the rest: the request needs changing, and the server already said how.
    setSaveError(error.message);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await save(editing ? editing.version : null);
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
          <Button type="submit" form="meeting-form" disabled={saving || conflict !== null}>
            {saving ? "Saving…" : editing ? "Save changes" : "Create meeting"}
          </Button>
        </>
      }
    >
      {saveError && (
        <p role="alert" className="mb-3 rounded-[10px] bg-surface-sunken px-3 py-2 text-xs text-muted-foreground">
          {saveError}
        </p>
      )}

      {conflict && (
        // The whole point of CP-D on this side: a 409 is a decision, not a toast.
        // The user is told who changed what, shown the current values, and given the
        // two choices that actually exist. Nothing is resolved automatically —
        // silently keeping either version is how an edit disappears without anyone
        // noticing.
        <div
          role="alert"
          aria-live="assertive"
          className="mb-4 rounded-[10px] border border-warning-emphasis/30 bg-warning-subtle px-3 py-3"
        >
          <p className="text-sm font-medium text-foreground">
            Someone else saved this meeting while you were editing.
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            You started from version {conflict.expected}; it is now version {conflict.current}.
          </p>

          <dl className="mt-3 space-y-1 text-xs">
            <div className="flex gap-2">
              <dt className="w-20 shrink-0 text-muted-foreground">Their title</dt>
              <dd className="text-foreground">{conflict.theirs.title}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="w-20 shrink-0 text-muted-foreground">Their location</dt>
              <dd className="text-foreground">{conflict.theirs.location ?? "—"}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="w-20 shrink-0 text-muted-foreground">Their status</dt>
              <dd className="text-foreground">{MEETING_STATUS_LABEL[conflict.theirs.status]}</dd>
            </div>
          </dl>

          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                // Take theirs: load the current values into the form and let the user
                // decide what to re-apply. Closing outright would throw away what they
                // typed, which is the same data loss from the other direction.
                const t = conflict.theirs;
                setTitle(t.title);
                setDate(t.scheduled_start ? toDateInput(t.scheduled_start) : todayInput());
                setStart(t.scheduled_start ? toTimeInput(t.scheduled_start) : "09:00");
                setEnd(t.scheduled_end ? toTimeInput(t.scheduled_end) : "10:00");
                setLocation(t.location ?? "");
                setStatus(t.status);
                setConflict(null);
              }}
            >
              Load their version
            </Button>
            <Button
              type="button"
              disabled={saving}
              onClick={() => {
                // Keep mine: re-run the same save against the version that is actually
                // current. Deliberately a button and not automatic — an overwrite the
                // user did not ask for is exactly what optimistic concurrency exists
                // to prevent.
                const against = conflict.current;
                setConflict(null);
                void save(against);
              }}
            >
              Keep my changes
            </Button>
          </div>
        </div>
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
            {/* Base UI's select rather than the native one: the native control
                renders its list with the OS's own styling, so it was the single
                surface in the app that ignored the Meridian design language.
                `items` is what lets the closed trigger show the LABEL while the
                form state stays the status code. */}
            <Select
              items={MEETING_STATUSES.map((s) => ({ label: MEETING_STATUS_LABEL[s], value: s }))}
              value={status}
              onValueChange={(next) => setStatus(next as MeetingStatus)}
            >
              <SelectTrigger
                id="mtg-status"
                className="h-10 w-full rounded-[12px] bg-surface-raised data-[size=default]:h-10"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  {MEETING_STATUSES.map((s) => (
                    <SelectItem key={s} value={s}>
                      {MEETING_STATUS_LABEL[s]}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
        </div>
      </form>
    </Dialog>
  );
}
