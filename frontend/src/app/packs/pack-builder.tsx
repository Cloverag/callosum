"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowDown, ArrowUp, FileText, Lock, Plus, Trash2 } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { FieldValue } from "@/components/ui/field-value";
import { withheld as withheldState } from "@/lib/field-state";
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
 * **It never totals items.** The server filters a pack to the caller's clearance and
 * renumbers (see `lib/packs.ts`), so a visible length would read as the pack's size. The
 * one figure shown is `withheld_items`, as the shared "N withheld" count (ADR-018,
 * #198), and nothing is derived from it.
 *
 * **Reordering is switched off when anything is withheld.** The server needs EVERY item
 * id to reorder, and this caller cannot see them all, so the request could only fail.
 * Saying why beats a button that always errors.
 *
 * **Every mutation is followed by a re-read.** Adding or removing an item bumps the
 * pack's `version`, so the version on screen after the call is stale, and publishing
 * with it is a 409 at best. The pack held here is always the one the server last sent.
 *
 * ---------------------------------------------------------------------------
 * PUBLISHING IS A TWO-STEP, IN ONE DIALOG
 * ---------------------------------------------------------------------------
 * Publish freezes the pack for good, so the button only opens a confirmation that
 * states which version is about to stand. It swaps the content of ONE dialog rather
 * than stacking a second modal on top (one focus trap, one Escape, no nesting) and, for
 * the same reason, never unmounts the dialog, so the focus moves below are not fought
 * by the dialog's own initial-focus.
 *
 * ---------------------------------------------------------------------------
 * FOCUS AND ANNOUNCEMENTS
 * ---------------------------------------------------------------------------
 * Every control that takes an action unmounts or moves when the action lands, which
 * drops focus to the page. So each action asks for focus somewhere deliberate, as a
 * sequenced request (asking twice for the same target still re-focuses), and says what
 * happened in a polite live region:
 *   - move: the same item's button, or its opposite if the row hit an end;
 *   - add / remove: the pack list (the control that had focus is gone);
 *   - Publish… → the confirmation's "Back"; Back → "Publish…"; published → the list.
 * Not exercised in a real browser; see the PR.
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
  const [notice, setNotice] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const [focus, setFocus] = useState<FocusRequest | null>(null);

  const listRef = useRef<HTMLOListElement>(null);
  const publishRef = useRef<HTMLButtonElement>(null);
  const backRef = useRef<HTMLButtonElement>(null);
  const moveRefs = useRef(new Map<string, HTMLButtonElement | null>());

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

  useEffect(() => {
    if (!focus) return;
    const target =
      focus.target === "list"
        ? listRef.current
        : focus.target === "publish"
          ? publishRef.current
          : focus.target === "back"
            ? backRef.current
            : moveRefs.current.get(focus.target);
    target?.focus();
  }, [focus]);

  /**
   * Runs one change, then re-reads the pack so `version` is current. Resolves with the
   * fresh pack and whether the change itself succeeded; `fresh` is null if the re-read
   * failed, in which case the pack on screen is known to be stale and the reader is told.
   */
  const run = useCallback(
    async (change: () => Promise<unknown>): Promise<{ ok: boolean; fresh: BoardPack | null }> => {
      setBusy(true);
      setError(null);
      setNotice(null);
      let ok = true;
      try {
        await change();
      } catch (e) {
        ok = false;
        setError(asApiError(e));
      }
      // Re-read even after a failure: a 409 means the copy on screen is stale, and a
      // retry from it would fail the same way.
      let fresh: BoardPack | null = null;
      try {
        fresh = await packsApi.get(pack.id);
        if (fresh) {
          setPack(fresh);
          onChanged(fresh);
        }
      } catch {
        // The write may have landed (or not); either way this copy can no longer be
        // trusted, so say so rather than leave a stale pack looking current. Publishing
        // from it would be refused on version anyway.
        setNotice(
          ok
            ? "Your change was saved, but the pack could not be reloaded. Close and reopen it before changing anything else."
            : "The pack could not be reloaded. Close and reopen it before changing anything else.",
        );
        // The notice replaces whatever the change reported: it is the more urgent fact.
        setError(null);
      } finally {
        setBusy(false);
      }
      return { ok, fresh };
    },
    [pack.id, onChanged],
  );

  const knownDocs = useMemo(() => [...documents, ...(material ?? [])], [documents, material]);
  const rows = resolveItems(pack.items, knownDocs);
  const inPack = new Set(pack.items.map((i) => i.document_id));
  const addable = (material ?? []).filter((d) => !inPack.has(d.id));
  const hasWithheld = pack.withheld_items > 0;
  const nameOf = (docId: string) => knownDocs.find((d) => d.id === docId)?.title ?? "A document";

  async function move(index: number, by: -1 | 1) {
    const ids = pack.items.map((i) => i.id);
    const movedId = ids[index];
    const name = nameOf(pack.items[index].document_id);
    const target = index + by;
    if (target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target], ids[index]];
    const { ok, fresh } = await run(() => packsApi.reorder(pack.id, ids));
    if (!ok || !fresh) return;
    const at = fresh.items.findIndex((i) => i.id === movedId);
    setAnnouncement(`${name} moved to position ${at + 1} of ${fresh.items.length}.`);
    // Same button, unless the row reached the end where that button is now disabled.
    const dir = by < 0 ? (at === 0 ? "down" : "up") : at === fresh.items.length - 1 ? "up" : "down";
    setFocus(focusRequest(`${movedId}:${dir}`));
  }

  async function add(d: Document) {
    const { ok } = await run(() => packsApi.addItem(pack.id, { document_id: d.id }));
    if (!ok) return;
    setAnnouncement(`${d.title} added to the pack.`);
    setFocus(focusRequest("list"));
  }

  async function remove(itemId: string, name: string) {
    const { ok } = await run(() => packsApi.removeItem(itemId));
    if (!ok) return;
    setAnnouncement(`${name} removed from the pack.`);
    setFocus(focusRequest("list"));
  }

  async function publish() {
    const { ok } = await run(() => packsApi.publish(pack.id, pack.version));
    if (!ok) return;
    setConfirming(false);
    setAnnouncement(`Version ${pack.version_no} published.`);
    setFocus(focusRequest("list"));
  }

  function openConfirm() {
    setConfirming(true);
    setFocus(focusRequest("back"));
  }

  function closeConfirm() {
    setConfirming(false);
    setFocus(focusRequest("publish"));
  }

  const meetingName = meeting?.title ?? "—";
  const problem = error ? serverMessage(error) : null;

  return (
    <Dialog
      open
      onClose={confirming ? (busy ? () => undefined : closeConfirm) : onClose}
      title={confirming ? `Publish version ${pack.version_no}?` : pack.title}
      description={
        confirming
          ? `“${pack.title}” for ${meetingName}.`
          : `${meetingName} · Version ${pack.version_no} · ${
              editable ? "Draft" : pack.status === "published" ? "Published" : "Locked"
            }`
      }
      className="max-w-2xl"
      footer={
        confirming ? (
          <>
            <Button ref={backRef} variant="secondary" onClick={closeConfirm} disabled={busy}>
              Back
            </Button>
            <Button loading={busy} onClick={() => void publish()}>
              Publish version {pack.version_no}
            </Button>
          </>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose}>
              Close
            </Button>
            {editable && (
              <Button ref={publishRef} onClick={openConfirm} disabled={busy}>
                Publish…
              </Button>
            )}
          </>
        )
      }
    >
      <p aria-live="polite" className="sr-only">
        {announcement}
      </p>

      {confirming ? (
        <div className="flex flex-col gap-3 text-sm text-muted-foreground">
          <p>
            Publishing freezes this version. Its contents can no longer be edited, and it is the
            version directors will read.
          </p>
          <p>
            To change it afterwards you issue version {pack.version_no + 1}; version {pack.version_no}{" "}
            stays on record as published.
          </p>
          <p>Publishing here does not send anything. Distribution is not part of this step.</p>
          {hasWithheld && <WithheldNote count={pack.withheld_items} />}
          {problem && (
            <p role="alert" className="text-danger">
              {problem}
            </p>
          )}
          {notice && <p role="alert">{notice}</p>}
        </div>
      ) : (
        <div className="flex flex-col gap-5">
          {problem && (
            <p role="alert" className="text-sm text-danger">
              {problem}
            </p>
          )}
          {notice && (
            <p role="alert" className="text-sm text-foreground">
              {notice}
            </p>
          )}

          <section aria-labelledby="pack-items-heading">
            <h3 id="pack-items-heading" className="text-xs font-medium text-muted-foreground">
              In this pack
            </h3>
            {rows.length === 0 ? (
              <p className="mt-2 text-sm text-muted-foreground">No documents to show in this pack.</p>
            ) : (
              <ol
                ref={listRef}
                tabIndex={-1}
                aria-labelledby="pack-items-heading"
                aria-busy={busy || undefined}
                className="mt-2 space-y-1.5 focus-visible:outline-none"
              >
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
                            ref={(el) => void moveRefs.current.set(`${item.id}:up`, el)}
                            variant="ghost"
                            size="sm"
                            aria-label={`Move ${name} up`}
                            disabled={busy || hasWithheld || index === 0}
                            onClick={() => void move(index, -1)}
                          >
                            <ArrowUp />
                          </Button>
                          <Button
                            ref={(el) => void moveRefs.current.set(`${item.id}:down`, el)}
                            variant="ghost"
                            size="sm"
                            aria-label={`Move ${name} down`}
                            disabled={busy || hasWithheld || index === rows.length - 1}
                            onClick={() => void move(index, 1)}
                          >
                            <ArrowDown />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            aria-label={`Remove ${name}`}
                            disabled={busy}
                            onClick={() => void remove(item.id, name)}
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
            {hasWithheld && <WithheldNote count={pack.withheld_items} className="mt-3" />}
            {hasWithheld && editable && (
              <p className="mt-2 text-xs text-muted-foreground">
                Reordering is unavailable: it needs every item, and some are above your clearance.
              </p>
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
                        onClick={() => void add(d)}
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
      )}
    </Dialog>
  );
}

/** ADR-018: how many items are above this reader's clearance, and that this is not all of it. */
function WithheldNote({ count, className }: { count: number; className?: string }) {
  return (
    <p className={`flex items-center gap-2 text-sm text-muted-foreground ${className ?? ""}`}>
      <Lock className="size-4 shrink-0" aria-hidden />
      <FieldValue state={withheldState<number>(count)} />
      <span>
        {count === 1 ? "document is" : "documents are"} above your clearance. This pack is not
        everything the board holds for this meeting.
      </span>
    </p>
  );
}

type FocusRequest = { target: string; seq: number };
let focusSeq = 0;
/** A fresh object per request, so asking twice for the same target still re-focuses. */
const focusRequest = (target: string): FocusRequest => ({ target, seq: ++focusSeq });
