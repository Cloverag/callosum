"use client";

import { useState } from "react";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { ApiError } from "@/lib/http";
import {
  documentsApi,
  DOC_TYPE_LABEL,
  INTAKE_SENSITIVITIES,
  SENSITIVITY_LABEL,
  type DocType,
  type Document,
  type Sensitivity,
} from "@/lib/documents";

const DOC_TYPES = Object.keys(DOC_TYPE_LABEL) as DocType[];

/**
 * What each level means, in the words the schema uses for it.
 *
 * `schema/postgres.sql:19-23` annotates every level with the material it is for —
 * "salary, legal, M&A" for confidential, "board packs, cap table" for investor. Those
 * annotations are the only thing that makes the choice answerable by someone who has
 * not read the schema, and the form is where that person is standing.
 */
const SENSITIVITY_HINT: Record<Sensitivity, string> = {
  0: "Press releases, public metrics",
  1: "Board packs, cap table, KPIs shared with the board",
  2: "Team-wide docs, product decisions",
  3: "Salary, legal, M&A, termination discussions",
  4: "Founder-only",
};

const field = "flex flex-col gap-1.5";
const label = "text-xs font-medium text-muted-foreground";
const control =
  "h-10 w-full rounded-[12px] border border-border bg-surface-raised px-3 text-sm text-foreground " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 " +
  "focus-visible:ring-offset-surface-raised";

/**
 * Filing a source document.
 *
 * ---------------------------------------------------------------------------
 * THE SENSITIVITY CONTROL CARRIES THREE DECISIONS FROM #143
 * ---------------------------------------------------------------------------
 * 1. **Nothing is pre-selected.** The field is required and starts empty, so the form
 *    cannot be submitted without a deliberate classification. Defaulting to `public`
 *    would look like a helpful convenience and would be the exact fail-open behaviour
 *    the API stopped doing — a document published to everyone because nobody chose.
 *
 * 2. **Four levels, not five.** `4 restricted` is reserved and intake refuses it, so
 *    offering it would produce a 422 for a choice the UI invited.
 *
 * 3. **The list is NOT filtered to the caller's clearance, and cannot be.** `/auth/me`
 *    deliberately withholds clearance — it is per-workspace and resolved per request,
 *    so publishing it to the browser would mean caching an authorization. The server
 *    refuses an over-clearance filing with a 403 that names the level the caller may
 *    use, and that message is surfaced verbatim rather than paraphrased.
 *
 *    A refusal is never retried at a lower level. Silently re-filing as `investor`
 *    what someone marked `confidential` would tell them their document is protected at
 *    a level it is not — the same reason the API refuses instead of clamping.
 */
export function IntakeDialog({
  open,
  onClose,
  onIngested,
}: {
  open: boolean;
  onClose: () => void;
  onIngested: (doc: Document) => void;
}) {
  const [title, setTitle] = useState("");
  const [docType, setDocType] = useState<DocType>("memo");
  const [rawText, setRawText] = useState("");
  const [sourceUri, setSourceUri] = useState("");
  // `null` is "not chosen", and it is distinct from level 0. This is the same
  // distinction `FieldState` draws on the read side: an absent choice is not a value.
  const [sensitivity, setSensitivity] = useState<Sensitivity | null>(null);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  // A boolean, not the server's message (#147). It used to hold `api.message` and
  // render it verbatim, which meant the screen disclosed whatever the API happened to
  // put in a 409 — fine today, and an open channel the moment that text changes.
  // Duplicate detection reveals that a match exists and nothing about what matched.
  const [isDuplicate, setIsDuplicate] = useState(false);

  const ready = title.trim() !== "" && rawText.trim() !== "" && sensitivity !== null;

  function reset() {
    setTitle("");
    setDocType("memo");
    setRawText("");
    setSourceUri("");
    setSensitivity(null);
    setError(null);
    setIsDuplicate(false);
  }

  async function submit() {
    if (!ready || sensitivity === null) return;
    setSubmitting(true);
    setError(null);
    setIsDuplicate(false);
    try {
      const doc = await documentsApi.intake({
        title: title.trim(),
        doc_type: docType,
        raw_text: rawText,
        sensitivity,
        source_uri: sourceUri.trim() || null,
      });
      onIngested(doc);
      reset();
      onClose();
    } catch (err) {
      const api = err instanceof ApiError ? err : new ApiError(0, "network", "Could not reach the server.");
      // A duplicate is not a failure. The content hash matched something already in
      // this workspace, which means the document is already in memory — the honest
      // report is recognition, not an error the user must fix.
      // The message is deliberately dropped rather than shown. See the state above.
      if (api.isConflict) setIsDuplicate(true);
      else setError(api);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Ingest a document"
      description="Paste the source text. Meridian chunks it, verifies every extracted fact against a quote in it, and files the rest for review."
      footer={
        <div className="flex items-center justify-end gap-3">
          <Button variant="secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!ready} loading={submitting}>
            Ingest
          </Button>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        <div className={field}>
          <label className={label} htmlFor="doc-title">Title</label>
          <Input id="doc-title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Q3 Board Meeting — transcript" />
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className={field}>
            <label className={label} htmlFor="doc-type">Type</label>
            <select id="doc-type" className={control} value={docType} onChange={(e) => setDocType(e.target.value as DocType)}>
              {DOC_TYPES.map((t) => (
                <option key={t} value={t}>{DOC_TYPE_LABEL[t]}</option>
              ))}
            </select>
          </div>

          <div className={field}>
            <label className={label} htmlFor="doc-sensitivity">
              Classification <span className="text-danger">*</span>
            </label>
            <select
              id="doc-sensitivity"
              className={cn(control, sensitivity === null && "text-muted-foreground")}
              value={sensitivity === null ? "" : String(sensitivity)}
              onChange={(e) => setSensitivity(e.target.value === "" ? null : (Number(e.target.value) as Sensitivity))}
            >
              {/* Deliberately empty and deliberately not disabled-and-hidden: the
                  reader must see that nothing has been chosen for them. */}
              <option value="">Choose a classification…</option>
              {INTAKE_SENSITIVITIES.map((level) => (
                <option key={level} value={level}>
                  {level} · {SENSITIVITY_LABEL[level]} — {SENSITIVITY_HINT[level]}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className={field}>
          <label className={label} htmlFor="doc-text">Source text</label>
          <textarea
            id="doc-text"
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            rows={10}
            placeholder="Paste the transcript, memo or email body…"
            className={cn(control, "h-auto resize-y py-2.5 font-mono text-[13px] leading-relaxed")}
          />
          <p className="text-xs text-subtle-foreground">
            Text only. File parsing (PDF, DOCX) is not built yet.
          </p>
        </div>

        <div className={field}>
          <label className={label} htmlFor="doc-source">Source link <span className="text-subtle-foreground">(optional)</span></label>
          <Input id="doc-source" value={sourceUri} onChange={(e) => setSourceUri(e.target.value)} placeholder="https://drive.google.com/…" />
        </div>

        {isDuplicate && (
          /* Fixed copy, carrying no metadata from the matched document — not its
             title, author, date, sensitivity or id (#147). A low-clearance member who
             submits leaked content must not learn what the board calls a confidential
             document merely because dedup fired. */
          <div role="status" className="rounded-[12px] border border-border-strong bg-surface-sunken px-4 py-3 text-sm text-foreground">
            <span className="font-medium">This document matches an existing document.</span>{" "}
            The same text is already in memory, so nothing was duplicated.
          </div>
        )}

        {error && (
          <div role="alert" className="rounded-[12px] border border-danger bg-surface-sunken px-4 py-3 text-sm text-foreground">
            {/* The server's own words. A 403 here names the level this caller may
                file at, and paraphrasing it to "permission denied" would throw away
                the only part that tells them what to do next. */}
            {error.message}
          </div>
        )}
      </div>
    </Dialog>
  );
}
