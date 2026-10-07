"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowDown, ArrowUp, FileText, Plus, Trash2 } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/http";
import { serverMessage } from "@/lib/error-text";
import { isEditable, packsApi, resolveItems, type BoardPack } from "@/lib/packs";
import type { Document } from "@/lib/documents";
import { meetingsApi, type Meeting } from "@/lib/meetings";

function asApiError(err: unknown): ApiError {
  return err instanceof ApiError ? err : new ApiError(0, "network", "Could not reach the server.");
}

/**
 * Builds a draft pack and publishes it.
 *
 * ---------------------------------------------------------------------------
 * WHAT THIS DOES NOT DO
 * ---------------------------------------------------------------------------
 * It does not generate sections, summaries or titles, and it adds no endpoint: every
 * call here is a route that already exists (`meridian/api/packs.py`). Items come only
 * from the meeting's assigned material, so a pack cannot be filled with a document the
 * meeting was never given.
 *
 * **It never shows or computes a total of items.** The server filters a pack to the
 * caller's clearance and renumbers (see `lib/packs.ts`), so a count here would describe
 * the caller's view and read as the pack's. Rows are listed; nothing is counted.
 *
 * **Every mutation is followed by a re-read.** Adding or removing an item bumps the
 * pack's `version`, so the version on screen after the call is stale, and publishing
 * with it is a 409 at best. The pack held here is always the one the server last sent.
 *
 * ---------------------------------------------------------------------------
 * PUBLISHING IS A TWO-STEP, IN ONE DIALOG
 * ---------------------------------------------------------------------------
 * Publish freezes the pack for good, so the button only opens a confirmation that
 * states which version is about to stand. It swaps the content of this dialog rather
 * than stacking a second modal on top: one focus trap, one Escape, no nesting.
 */
export function PackBuilder({
  pack: initial,
  meeting,
  documents,
  onChanged,
  onClose,
}: {
  pack: BoardPack;
  meeting: Meeting | undefined;
  /** For resolving titles of items already in the pack. */
  documents: Document[];
  /** Called with the server's latest copy after every successful change. */
  onChanged: (pack: BoardPack) => void;
  onClose: () => void;
}) {
  const [pack, setPack] = useState(initial);
  const [material, setMaterial] = useState<Document[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [confirming, setConfirming] = useState(false);

  const editable = isEditable(pack, meeting?.status);

  useEffect(() => {
    let stale = false;
    meetingsApi
      .material(initial.meeting_id)
      .then((m) => !stale && setMaterial(m.documents))
      .catch((e) => {
        if (stale) return;
        setMaterial([]);
        setError(asApiError(e));
      });
    return () => {
      stale = true;
    };
  }, [initial.meeting_id]);

  /** Runs one change, then re-reads the pack so `version` is current. */
  const run = useCallback(
    async (change: () => Promise<unknown>) => {
      setBusy(true);
      setError(null);
      try {
        await change();
      } catch (e) {
        setError(asApiError(e));
      }
      // Re-read even after a failure: a 409 means the copy on screen is stale, and a
      // retry from it would fail the same way.
      try {
        const fresh = await packsApi.get(pack.id);
        if (fresh) {
          setPack(fresh);
          onChanged(fresh);
        }
      } finally {
        setBusy(false);
      }
    },
    [pack.id, onChanged],
  );

  const knownDocs = useMemo(() => [...documents, ...(material ?? [])], [documents, material]);
  const rows = resolveItems(pack.items, knownDocs);
  const inPack = new Set(pack.items.map((i) => i.document_id));
  const addable = (material ?? []).filter((d) => !inPack.has(d.id));

  function move(index: number, by: -1 | 1) {
    const ids = pack.items.map((i) => i.id);
    const target = index + by;
    if (target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target], ids[index]];
    void run(() => packsApi.reorder(pack.id, ids));
  }

  const meetingName = meeting?.title ?? "—";

  if (confirming) {
    return (
      <Dialog
        open
        onClose={() => (busy ? undefined : setConfirming(false))}
        title={`Publish version ${pack.version_no}?`}
        description={
          <>
            “{pack.title}” for {meetingName}.
          </>
        }
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirming(false)} disabled={busy}>
              Back
            </Button>
            <Button
              loading={busy}
              onClick={() =>
                void run(async () => {
                  await packsApi.publish(pack.id, pack.version);
                  setConfirming(false);
                })
              }
            >
              Publish version {pack.version_no}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3 text-sm text-muted-foreground">
          <p>
            Publishing freezes this version. Its contents can no longer be edited, and it is the
            version directors will read.
          </p>
          <p>
            To change it afterwards you issue version {pack.version_no + 1}; version{" "}
            {pack.version_no} stays on record as published.
          </p>
          <p>
            Publishing here does not send anything. Distribution is not part of this step.
          </p>
          {error && (
            <p role="alert" className="text-danger">
              {serverMessage(error)}
            </p>
          )}
        </div>
      </Dialog>
    );
  }

  return (
    <Dialog
      open
      onClose={onClose}
      title={pack.title}
      description={`${meetingName} · Version ${pack.version_no} · ${
        editable ? "Draft" : pack.status === "published" ? "Published" : "Locked"
      }`}
      className="max-w-2xl"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
          {editable && (
            <Button onClick={() => setConfirming(true)} disabled={busy}>
              Publish…
            </Button>
          )}
        </>
      }
    >
      <div className="flex flex-col gap-5">
        {error && (
          <p role="alert" className="text-sm text-danger">
            {serverMessage(error)}
          </p>
        )}

        <section aria-labelledby="pack-items-heading">
          <h3 id="pack-items-heading" className="text-xs font-medium text-muted-foreground">
            In this pack
          </h3>
          {rows.length === 0 ? (
            <p className="mt-2 text-sm text-muted-foreground">No documents to show in this pack.</p>
          ) : (
            <ol className="mt-2 space-y-1.5">
              {rows.map(({ item, document }, index) => {
                const name = document?.title ?? "Document reference could not be resolved";
                return (
                  <li
                    key={item.id}
                    className="flex items-center gap-2 rounded-[10px] border border-border px-3 py-2"
                  >
                    <FileText className="size-3.5 shrink-0 text-subtle-foreground" aria-hidden />
                    <span className="min-w-0 flex-1 truncate text-sm text-foreground">{name}</span>
                    {editable && (
                      <span className="flex shrink-0 items-center gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          aria-label={`Move ${name} up`}
                          disabled={busy || index === 0}
                          onClick={() => move(index, -1)}
                        >
                          <ArrowUp />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          aria-label={`Move ${name} down`}
                          disabled={busy || index === rows.length - 1}
                          onClick={() => move(index, 1)}
                        >
                          <ArrowDown />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          aria-label={`Remove ${name}`}
                          disabled={busy}
                          onClick={() => void run(() => packsApi.removeItem(item.id))}
                        >
                          <Trash2 />
                        </Button>
                      </span>
                    )}
                  </li>
                );
              })}
            </ol>
          )}
        </section>

        {editable && (
          <section aria-labelledby="pack-add-heading">
            <h3 id="pack-add-heading" className="text-xs font-medium text-muted-foreground">
              Add from this meeting’s material
            </h3>
            {material === null ? (
              <p className="mt-2 text-sm text-muted-foreground">Loading material…</p>
            ) : addable.length === 0 ? (
              <p className="mt-2 text-sm text-muted-foreground">
                {material.length === 0
                  ? "No material has been assigned to this meeting."
                  : "Everything assigned to this meeting is already in the pack."}
              </p>
            ) : (
              <ul className="mt-2 space-y-1.5">
                {addable.map((d) => (
                  <li
                    key={d.id}
                    className="flex items-center gap-2 rounded-[10px] border border-border px-3 py-2"
                  >
                    <span className="min-w-0 flex-1 truncate text-sm text-foreground">{d.title}</span>
                    <Button
                      variant="secondary"
                      size="sm"
                      aria-label={`Add ${d.title}`}
                      disabled={busy}
                      onClick={() => void run(() => packsApi.addItem(pack.id, { document_id: d.id }))}
                    >
                      <Plus /> Add
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {!editable && (
          <p className="text-sm text-muted-foreground">
            {pack.status === "published"
              ? "This version is published and cannot be edited. Issue a new version to change it."
              : "This pack cannot be edited while its meeting is in progress, complete or cancelled."}
          </p>
        )}
      </div>
    </Dialog>
  );
}
