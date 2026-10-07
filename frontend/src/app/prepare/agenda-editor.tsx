"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronUp, Pencil, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/http";
import { serverMessage } from "@/lib/error-text";
import { agendaApi, totalMinutes, type AgendaItem, type AgendaItemPatch } from "@/lib/agenda";

/**
 * The meeting's current agenda, editable (P5 CP5D).
 *
 * The list always shows what the server reported. An edit returns the item; a reorder
 * returns the whole agenda (and re-versions every item, so a stale local copy would 409).
 * A removal is the one write answered locally: the server only runs
 * `SET position = position - 1` on the tail and changes no version, so renumbering here
 * is exact, and a second request that could fail after the delete landed is avoided.
 *
 * Reordering is "move up / move down" buttons rather than drag, so the keyboard path is
 * the same path as the pointer path (WCAG 2.2 AA, `rules.md` §6). Focus is put back
 * deliberately after every write, and each change is announced in a live region, because
 * a moved or removed row otherwise drops focus to the top of the page.
 */
export function AgendaEditor({
  meetingId,
  items,
  onChange,
}: {
  meetingId: string;
  items: AgendaItem[];
  onChange: (items: AgendaItem[]) => void;
}) {
  const [failed, setFailed] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  // A fresh, sequenced object per request, so asking twice still re-focuses.
  const [focus, setFocus] = useState<FocusRequest | null>(null);
  const listRef = useRef<HTMLOListElement>(null);

  /** Resolves true when the write landed, so an edit form stays open (and keeps what
   *  was typed) when it did not. */
  async function run(write: () => Promise<AgendaItem[]>, done: (next: AgendaItem[]) => void) {
    setBusy(true);
    setFailed(null);
    try {
      const next = await write();
      onChange(next);
      done(next);
      return true;
    } catch (e) {
      setFailed(describeFailure(e));
      return false;
    } finally {
      setBusy(false);
    }
  }

  const move = (index: number, by: -1 | 1) => {
    const item = items[index];
    const ids = items.map((i) => i.id);
    [ids[index], ids[index + by]] = [ids[index + by], ids[index]];
    return run(
      () => agendaApi.reorder(meetingId, ids),
      (next) => {
        const at = next.findIndex((i) => i.id === item.id);
        setAnnouncement(`"${item.title}" moved to position ${at + 1} of ${next.length}.`);
        // Keep focus on the button pressed, unless the row reached the end where that
        // button is now disabled; then the opposite one.
        const control = by < 0 ? (at === 0 ? "down" : "up") : at === next.length - 1 ? "up" : "down";
        setFocus(focusRequest(item.id, control));
      },
    );
  };

  const save = (item: AgendaItem, edit: AgendaEdit) => {
    const patch = changedFields(item, edit);
    if (patch === null) return Promise.resolve(true); // nothing changed: no write, no audit event
    return run(
      async () => {
        const updated = await agendaApi.update(item.id, { expected_version: item.version, ...patch });
        return items.map((i) => (i.id === updated.id ? updated : i));
      },
      () => setAnnouncement(`"${edit.title}" saved.`),
    );
  };

  const remove = (item: AgendaItem) =>
    run(
      async () => {
        await agendaApi.remove(item.id, item.version);
        return items
          .filter((i) => i.id !== item.id)
          .map((i) => (i.position > item.position ? { ...i, position: i.position - 1 } : i));
      },
      () => {
        setAnnouncement(`"${item.title}" removed from the agenda.`);
        listRef.current?.focus();
      },
    );

  const timed = items.filter((i) => i.duration_minutes !== null).length;

  return (
    <div>
      <p aria-live="polite" className="sr-only">
        {announcement}
      </p>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nothing is on the agenda yet.</p>
      ) : (
        <>
          <ol
            ref={listRef}
            tabIndex={-1}
            aria-label="Agenda"
            aria-busy={busy || undefined}
            className="space-y-2 focus-visible:outline-none"
          >
            {items.map((item, index) => (
              <AgendaRow
                key={item.id}
                item={item}
                first={index === 0}
                last={index === items.length - 1}
                disabled={busy}
                focus={focus?.id === item.id ? focus : null}
                onMove={(by) => move(index, by)}
                onSave={(edit) => save(item, edit)}
                onRemove={() => remove(item)}
              />
            ))}
          </ol>
          <p className="mt-3 text-xs text-muted-foreground">
            <span className="tabular-nums text-foreground">{totalMinutes(items)}</span> min timeboxed
            across <span className="tabular-nums">{timed}</span> of{" "}
            <span className="tabular-nums">{items.length}</span> items
            {timed < items.length && " — untimed items are not counted"}
          </p>
        </>
      )}
      {failed && (
        <p role="alert" className="mt-2 text-xs text-danger-emphasis">
          {failed}
        </p>
      )}
    </div>
  );
}

type Control = "up" | "down" | "edit" | "remove";
type FocusRequest = { id: string; control: Control; seq: number };
let focusSeq = 0;
const focusRequest = (id: string, control: Control): FocusRequest => ({ id, control, seq: ++focusSeq });
type AgendaEdit = { title: string; duration_minutes: number | null; presenter: string | null };

/** Only the fields that differ, so the audit trail's `changed_fields` (#227) records what
 *  the reader actually changed. Null when nothing did. */
export function changedFields(item: AgendaItem, edit: AgendaEdit): Omit<AgendaItemPatch, "expected_version"> | null {
  const patch: Omit<AgendaItemPatch, "expected_version"> = {};
  if (edit.title !== item.title) patch.title = edit.title;
  if (edit.duration_minutes !== item.duration_minutes) patch.duration_minutes = edit.duration_minutes;
  if (edit.presenter !== (item.presenter?.trim() || null)) patch.presenter = edit.presenter;
  return Object.keys(patch).length === 0 ? null : patch;
}

function describeFailure(e: unknown): string {
  if (!(e instanceof ApiError)) return "Could not reach the server.";
  if (e.isStale) return "Someone else changed the agenda. Reload the page to see the latest version.";
  // agenda.py locks the agenda for in_progress, completed and cancelled meetings.
  if (e.isUnretryableConflict)
    return "The agenda can no longer change — the meeting is in progress, completed or cancelled.";
  return serverMessage(e);
}

function AgendaRow({
  item,
  first,
  last,
  disabled,
  focus,
  onMove,
  onSave,
  onRemove,
}: {
  item: AgendaItem;
  first: boolean;
  last: boolean;
  disabled: boolean;
  focus: FocusRequest | null;
  onMove: (by: -1 | 1) => void;
  onSave: (edit: AgendaEdit) => Promise<boolean>;
  onRemove: () => Promise<boolean>;
}) {
  const [mode, setMode] = useState<"view" | "edit" | "confirm-remove">("view");
  const [returnTo, setReturnTo] = useState<FocusRequest | null>(null);
  const upRef = useRef<HTMLButtonElement>(null);
  const downRef = useRef<HTMLButtonElement>(null);
  const editRef = useRef<HTMLButtonElement>(null);
  const removeRef = useRef<HTMLButtonElement>(null);
  const keep = useRef<HTMLButtonElement>(null);

  // The newer of the parent's request (after a move) and this row's own (after an edit).
  const request = !focus ? returnTo : !returnTo ? focus : focus.seq > returnTo.seq ? focus : returnTo;
  useEffect(() => {
    if (!request || mode !== "view") return;
    ({ up: upRef, down: downRef, edit: editRef, remove: removeRef })[request.control].current?.focus();
  }, [request, mode]);

  useEffect(() => {
    if (mode === "confirm-remove") keep.current?.focus();
  }, [mode]);

  const back = (control: Control) => {
    setMode("view");
    setReturnTo(focusRequest(item.id, control));
  };

  if (mode === "edit") {
    return (
      <li className="rounded-[12px] border border-border px-4 py-3">
        <EditForm
          item={item}
          disabled={disabled}
          onCancel={() => back("edit")}
          onSave={async (edit) => {
            if (await onSave(edit)) back("edit");
          }}
        />
      </li>
    );
  }

  return (
    <li className="flex items-start justify-between gap-4 rounded-[12px] border border-border px-4 py-3">
      <div className="min-w-0">
        <p className="text-sm font-medium text-foreground">
          <span className="mr-2 tabular-nums text-subtle-foreground">{item.position}</span>
          {item.title}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          {item.duration_minutes !== null ? `${item.duration_minutes} min` : "Untimed"}
          {" · "}
          {item.presenter?.trim() ? item.presenter : "No presenter"}
        </p>
      </div>
      {mode === "confirm-remove" ? (
        <div className="flex shrink-0 items-center gap-2" role="group" aria-label={`Remove "${item.title}"?`}>
          <span className="text-xs text-foreground">Remove this item?</span>
          <Button variant="danger" size="sm" disabled={disabled} onClick={onRemove}>
            Remove
          </Button>
          <Button ref={keep} variant="ghost" size="sm" onClick={() => back("remove")}>
            Keep
          </Button>
        </div>
      ) : (
        <div className="flex shrink-0 items-center gap-1">
          <Button ref={upRef} variant="ghost" size="sm" disabled={disabled || first} onClick={() => onMove(-1)} aria-label={`Move "${item.title}" up`}>
            <ChevronUp />
          </Button>
          <Button ref={downRef} variant="ghost" size="sm" disabled={disabled || last} onClick={() => onMove(1)} aria-label={`Move "${item.title}" down`}>
            <ChevronDown />
          </Button>
          <Button ref={editRef} variant="ghost" size="sm" disabled={disabled} onClick={() => setMode("edit")} aria-label={`Edit "${item.title}"`}>
            <Pencil />
          </Button>
          <Button ref={removeRef} variant="ghost" size="sm" disabled={disabled} onClick={() => setMode("confirm-remove")} aria-label={`Remove "${item.title}"`}>
            <Trash2 />
          </Button>
        </div>
      )}
    </li>
  );
}

function EditForm({
  item,
  disabled,
  onCancel,
  onSave,
}: {
  item: AgendaItem;
  disabled: boolean;
  onCancel: () => void;
  onSave: (edit: AgendaEdit) => Promise<void>;
}) {
  const [title, setTitle] = useState(item.title);
  const [minutes, setMinutes] = useState(item.duration_minutes?.toString() ?? "");
  const [presenter, setPresenter] = useState(item.presenter ?? "");

  const parsed = minutes.trim() === "" ? null : Number(minutes);
  const minutesValid = parsed === null || (Number.isInteger(parsed) && parsed > 0);
  const titleValid = title.trim() !== "";

  return (
    <form
      className="grid gap-3 sm:grid-cols-[1fr_8rem_12rem]"
      onKeyDown={(e) => {
        if (e.key === "Escape") onCancel();
      }}
      onSubmit={(e) => {
        e.preventDefault();
        if (!titleValid || !minutesValid) return;
        void onSave({
          title: title.trim(),
          duration_minutes: parsed,
          presenter: presenter.trim() || null,
        });
      }}
    >
      <label className="text-xs text-muted-foreground">
        Title
        {/* autoFocus: focus moves into the form the reader just opened. */}
        <Input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} error={!titleValid} required className="mt-1" />
      </label>
      <label className="text-xs text-muted-foreground">
        Minutes
        <Input
          value={minutes}
          onChange={(e) => setMinutes(e.target.value)}
          inputMode="numeric"
          error={!minutesValid}
          placeholder="Untimed"
          className="mt-1"
        />
      </label>
      <label className="text-xs text-muted-foreground">
        Presenter
        <Input value={presenter} onChange={(e) => setPresenter(e.target.value)} placeholder="None" className="mt-1" />
      </label>
      {!minutesValid && (
        <p role="alert" className="text-xs text-danger-emphasis sm:col-span-3">
          Minutes must be a whole number above zero, or empty for an untimed item.
        </p>
      )}
      <div className="flex gap-2 sm:col-span-3">
        <Button type="submit" size="sm" loading={disabled} disabled={!titleValid || !minutesValid}>
          Save
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
