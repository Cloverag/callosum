"use client";

import { useState } from "react";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { ApiError } from "@/lib/http";
import { serverMessage } from "@/lib/error-text";
import { PACK_LOCKED_MEETING_STATUSES, packsApi, type BoardPack } from "@/lib/packs";
import type { Meeting } from "@/lib/meetings";

const field = "flex flex-col gap-1.5";
const label = "text-xs font-medium text-muted-foreground";
const control =
  "h-10 w-full rounded-[12px] border border-border bg-surface-raised px-3 text-sm text-foreground " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 " +
  "focus-visible:ring-offset-surface-raised";

/**
 * Starts a draft pack for a meeting that has not begun, or — given `supersedes` — issues
 * the next version of a published one.
 *
 * Two modes in one form for the reason `IntakeDialog` gives: a new version IS a create
 * plus a link, with the same title rule and the same refusals.
 *
 * **Nothing is pre-selected in create mode.** The meeting is a deliberate choice; a
 * default would file the pack against whichever meeting happened to sort first. A new
 * version starts from the published title because the title is the one field the
 * author is about to change, not a value invented for them.
 *
 * Meetings the server would refuse (`in_progress`, `completed`, `cancelled`) are not
 * offered. That is a convenience; the server enforces it regardless.
 */
export function PackCreateDialog({
  meetings,
  supersedes,
  onCreated,
  onClose,
}: {
  meetings: Meeting[];
  supersedes?: BoardPack;
  onCreated: (created: BoardPack, superseded: BoardPack | null) => void;
  onClose: () => void;
}) {
  const [meetingId, setMeetingId] = useState(supersedes?.meeting_id ?? "");
  const [title, setTitle] = useState(supersedes?.title ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const offered = meetings.filter((m) => !PACK_LOCKED_MEETING_STATUSES.has(m.status));
  const ready = meetingId !== "" && title.trim() !== "";

  async function submit() {
    if (!ready) return;
    setBusy(true);
    setError(null);
    try {
      if (supersedes) {
        const out = await packsApi.supersede(supersedes.id, {
          new_title: title.trim(),
          expected_version: supersedes.version,
        });
        onCreated(out.replacement, out.superseded);
      } else {
        onCreated(await packsApi.create({ meeting_id: meetingId, title: title.trim() }), null);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, "network", "Could not reach the server."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open
      onClose={onClose}
      title={supersedes ? `Issue version ${supersedes.version_no + 1}` : "New board pack"}
      description={
        supersedes
          ? `A new draft that starts from version ${supersedes.version_no}’s documents. Version ${supersedes.version_no} stays on record as published.`
          : "A draft you fill from the meeting’s assigned material."
      }
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!ready} loading={busy}>
            {supersedes ? "Create draft" : "Create pack"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {!supersedes && (
          <div className={field}>
            <label className={label} htmlFor="pack-meeting">
              Meeting
            </label>
            <select
              id="pack-meeting"
              className={cn(control, meetingId === "" && "text-muted-foreground")}
              value={meetingId}
              onChange={(e) => setMeetingId(e.target.value)}
            >
              <option value="">Choose a meeting…</option>
              {offered.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.title}
                </option>
              ))}
            </select>
          </div>
        )}
        <div className={field}>
          <label className={label} htmlFor="pack-title">
            Title
          </label>
          <Input id="pack-title" value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
        {error && (
          <p role="alert" className="text-sm text-danger">
            {serverMessage(error)}
          </p>
        )}
      </div>
    </Dialog>
  );
}
