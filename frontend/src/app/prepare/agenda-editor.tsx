"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, Pencil, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/http";
import { serverMessage } from "@/lib/error-text";
import { agendaApi, totalMinutes, type AgendaItem } from "@/lib/agenda";

/**
 * The meeting's current agenda, editable (P5 CP5D).
 *
 * Every write goes to the server and the list is replaced with what the server
 * returns: an edit returns the item, a reorder returns the whole agenda, and a removal
 * is followed by a re-list because the server renumbers the items after the gap.
 * (It does not bump their versions, so renumbering locally would also work; the
 * re-list is chosen so the page never shows an order the server did not report.)
 *
 * Reordering is "move up / move down" buttons rather than drag, so the keyboard path is
 * the same path as the pointer path (WCAG 2.2 AA, `rules.md` §6).
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

  /** Resolves true when the write landed, so an edit form stays open (and keeps what
   *  was typed) when it did not. */
  async function run(write: () => Promise<AgendaItem[]>): Promise<boolean> {
    setBusy(true);
    setFailed(null);
    try {
      onChange(await write());
      return true;
    } catch (e) {
      setFailed(describeFailure(e));
      return false;
    } finally {
      setBusy(false);
    }
  }

  const move = (index: number, by: -1 | 1) =>
    run(() => {
      const ids = items.map((i) => i.id);
      [ids[index], ids[index + by]] = [ids[index + by], ids[index]];
      return agendaApi.reorder(meetingId, ids);
    });

  const save = (item: AgendaItem, patch: AgendaEdit) =>
    run(async () => {
      const updated = await agendaApi.update(item.id, { expected_version: item.version, ...patch });
      return items.map((i) => (i.id === updated.id ? updated : i));
    });

  const remove = (item: AgendaItem) =>
    run(async () => {
      await agendaApi.remove(item.id, item.version);
      return agendaApi.list(meetingId);
    });

  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">Nothing is on the agenda yet.</p>;
  }

  const timed = items.filter((i) => i.duration_minutes !== null).length;

  return (
    <div>
      <ol className="space-y-2" aria-busy={busy || undefined}>
        {items.map((item, index) => (
          <AgendaRow
            key={item.id}
            item={item}
            first={index === 0}
            last={index === items.length - 1}
            disabled={busy}
            onMove={(by) => move(index, by)}
            onSave={(patch) => save(item, patch)}
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
      {failed && (
        <p role="alert" className="mt-2 text-xs text-danger-emphasis">
          {failed}
        </p>
      )}
    </div>
  );
}

type AgendaEdit = { title: string; duration_minutes: number | null; presenter: string | null };

function describeFailure(e: unknown): string {
  if (!(e instanceof ApiError)) return "Could not reach the server.";
  if (e.isStale) return "Someone else changed the agenda. Reload the page to see the latest version.";
  if (e.isUnretryableConflict) return "The agenda is locked — the meeting has already started.";
  return serverMessage(e);
}

function AgendaRow({
  item,
  first,
  last,
  disabled,
  onMove,
  onSave,
  onRemove,
}: {
  item: AgendaItem;
  first: boolean;
  last: boolean;
  disabled: boolean;
  onMove: (by: -1 | 1) => void;
  onSave: (patch: AgendaEdit) => Promise<boolean>;
  onRemove: () => Promise<boolean>;
}) {
  const [mode, setMode] = useState<"view" | "edit" | "confirm-remove">("view");

  if (mode === "edit") {
    return (
      <li className="rounded-[12px] border border-border px-4 py-3">
        <EditForm
          item={item}
          disabled={disabled}
          onCancel={() => setMode("view")}
          onSave={async (patch) => {
            if (await onSave(patch)) setMode("view");
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
        <div className="flex shrink-0 items-center gap-2">
          <span className="text-xs text-foreground">Remove this item?</span>
          <Button variant="danger" size="sm" disabled={disabled} onClick={onRemove}>
            Remove
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setMode("view")}>
            Keep
          </Button>
        </div>
      ) : (
        <div className="flex shrink-0 items-center gap-1">
          <Button variant="ghost" size="sm" disabled={disabled || first} onClick={() => onMove(-1)} aria-label={`Move "${item.title}" up`}>
            <ChevronUp />
          </Button>
          <Button variant="ghost" size="sm" disabled={disabled || last} onClick={() => onMove(1)} aria-label={`Move "${item.title}" down`}>
            <ChevronDown />
          </Button>
          <Button variant="ghost" size="sm" disabled={disabled} onClick={() => setMode("edit")} aria-label={`Edit "${item.title}"`}>
            <Pencil />
          </Button>
          <Button variant="ghost" size="sm" disabled={disabled} onClick={() => setMode("confirm-remove")} aria-label={`Remove "${item.title}"`}>
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
  onSave: (patch: AgendaEdit) => Promise<void>;
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
        <Input value={title} onChange={(e) => setTitle(e.target.value)} error={!titleValid} required className="mt-1" />
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
