"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronDown, FileText, History, Upload } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { LoadFailed, asApiError } from "@/components/ui/load-failed";
import type { ApiError } from "@/lib/http";
import { cn } from "@/lib/utils";
import {
  documentsApi,
  DOC_TYPE_LABEL,
  SENSITIVITY_LABEL,
  type Document,
  type DocType,
  type QuarantineItem,
  type Sensitivity,
} from "@/lib/documents";
import { IntakeDialog } from "./intake-dialog";
import { QuarantineList } from "./quarantine-list";
import { VersionChain } from "./version-chain";

/**
 * Sensitivity as a chip tone.
 *
 * Deliberately monotonic: the higher the level, the louder it reads. A reader
 * scanning the list must be able to see which rows are confidential without reading
 * the labels, because the failure this guards against is treating a restricted
 * document as an ordinary one.
 */
const SENSITIVITY_TONE: Record<Sensitivity, "neutral" | "info" | "warning" | "danger"> = {
  0: "neutral",
  1: "info",
  2: "info",
  3: "warning",
  4: "danger",
};

const rowAction =
  "inline-flex items-center gap-1 rounded-[12px] px-2 py-1 text-xs font-medium text-muted-foreground " +
  "transition-colors duration-(--duration-hover) hover:bg-surface-sunken hover:text-foreground " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[] | null>(null);
  const [quarantine, setQuarantine] = useState<QuarantineItem[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [intakeOpen, setIntakeOpen] = useState(false);
  const [tab, setTab] = useState<"documents" | "quarantine">("documents");
  // The document being revised, or null for an ordinary intake. One dialog serves both.
  const [revising, setRevising] = useState<Document | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = useCallback(() => {
    documentsApi.list().then(setDocuments).catch((e) => setError(asApiError(e)));
    // Quarantine failing must not blank the document list — they are separate
    // reads and a reader can act on one without the other.
    documentsApi.quarantine().then(setQuarantine).catch(() => setQuarantine([]));
  }, []);

  useEffect(load, [load]);

  const onIngested = useCallback((doc: Document, supersededId: string | null) => {
    setDocuments((prev) => {
      const next = prev ? [doc, ...prev] : [doc];
      // The predecessor's `superseded_by_id` changed server-side. Patching it here rather
      // than refetching keeps the badge honest without a second round trip — and the
      // value is not invented: this caller just filed the revision, so they are cleared
      // for it and the server would return exactly this id.
      return supersededId
        ? next.map((d) => (d.id === supersededId ? { ...d, superseded_by_id: doc.id } : d))
        : next;
    });
    // Extraction runs during intake, so a new document can add quarantine rows.
    documentsApi.quarantine().then(setQuarantine).catch(() => undefined);
  }, []);

  const closeDialog = useCallback(() => {
    setIntakeOpen(false);
    setRevising(null);
  }, []);

  const startRevision = useCallback((doc: Document) => {
    setRevising(doc);
    setIntakeOpen(true);
  }, []);

  const counts = useMemo(
    () => ({ documents: documents?.length ?? null, quarantine: quarantine?.length ?? null }),
    [documents, quarantine],
  );

  return (
    <div className="p-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <PageHeader
          title="Documents"
          description="Every source the graph was built from, and everything the verifier refused."
          icon={<FileText />}
        />
        <Button onClick={() => setIntakeOpen(true)}>
          <Upload className="size-4" />
          Ingest document
        </Button>
      </div>

      {error && (
        <div className="mt-6">
          <LoadFailed what="Documents" error={error} />
        </div>
      )}

      {/* Quarantine is a peer of the document list, not a footnote below it. The
          rejected extractions are the evidence that the accepted ones were checked. */}
      <div className="mt-6 flex gap-1 border-b border-border" role="tablist">
        {(["documents", "quarantine"] as const).map((key) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={
              "-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus " +
              (tab === key
                ? "border-accent text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground")
            }
          >
            {key === "documents" ? "Documents" : "Quarantine"}
            {counts[key] !== null && (
              <span className="ml-2 tabular-nums text-subtle-foreground">{counts[key]}</span>
            )}
          </button>
        ))}
      </div>

      <div className="mt-6">
        {tab === "documents" ? (
          <DocumentList
            documents={documents}
            onIngest={() => setIntakeOpen(true)}
            onRevise={startRevision}
            expanded={expanded}
            onToggle={(id) => setExpanded((prev) => (prev === id ? null : id))}
          />
        ) : (
          <QuarantineList items={quarantine} />
        )}
      </div>

      <IntakeDialog
        open={intakeOpen}
        onClose={closeDialog}
        onIngested={onIngested}
        supersedes={revising}
      />
    </div>
  );
}

function DocumentList({
  documents,
  onIngest,
  onRevise,
  expanded,
  onToggle,
}: {
  documents: Document[] | null;
  onIngest: () => void;
  onRevise: (doc: Document) => void;
  expanded: string | null;
  onToggle: (id: string) => void;
}) {
  if (documents === null) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-16 rounded-[16px] bg-surface-sunken" />
        ))}
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <Card className="px-6 py-16 text-center">
        <span className="mx-auto flex size-12 items-center justify-center rounded-full border border-border bg-surface-elevated text-muted-foreground">
          <FileText className="size-6" />
        </span>
        {/* h2: PageHeader renders the h1 and this is the only heading beneath it,
            so an h3 skips a level. Kept from #112. */}
        <h2 className="mt-3 text-sm font-medium text-foreground">No documents yet</h2>
        <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">
          Ingest a transcript, memo or email to build institutional memory. Every source
          stays attributable and permission-scoped.
        </p>
        {/* The empty state carries the action that ends it — state 2 of the seven. */}
        <Button className="mt-4" onClick={onIngest}>
          <Upload className="size-4" />
          Ingest document
        </Button>
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden">
      <ul className="divide-y divide-border">
        {documents.map((doc) => {
          const isOpen = expanded === doc.id;
          const superseded = doc.superseded_by_id !== null;
          return (
            <li key={doc.id}>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3.5">
                <span
                  className={cn(
                    // `basis-[18rem]` with `flex-wrap` on the row, NOT `min-w-0`.
                    //
                    // A browser pass found this: `min-w-0 flex-1` lets the title collapse
                    // to whatever is left after the badges, type, date and two actions have
                    // taken theirs. On a 1280px window with the sidebar and the AI rail open
                    // — the default — titles rendered as "V..", "Ven..." and "Q3 r...".
                    // Every test passed, because a truncated title is still in the DOM and
                    // `toBeInTheDocument()` cannot see a two-character column.
                    //
                    // A flex basis makes the row wrap the METADATA to a second line instead
                    // of shrinking the one thing a reader scans by. `truncate` still applies
                    // past 18rem, so a very long title degrades rather than reflowing forever.
                    "flex-1 basis-[18rem] truncate text-sm font-medium",
                    // Superseded rows read quieter, because they are still the record and
                    // still readable — the point is that they are no longer in force, not
                    // that they are less real. Nothing is hidden or struck through.
                    superseded ? "text-muted-foreground" : "text-foreground",
                  )}
                >
                  {doc.title}
                </span>

                {/* Only above revision 1. A "v1" on every row is noise that makes the
                    one badge that matters harder to see. */}
                {doc.revision > 1 && (
                  <span className="tabular-nums text-xs font-semibold text-muted-foreground">
                    v{doc.revision}
                  </span>
                )}
                {superseded && <Badge tone="neutral">Superseded</Badge>}

                <span className="text-xs text-muted-foreground">
                  {DOC_TYPE_LABEL[doc.doc_type as DocType] ?? doc.doc_type}
                </span>
                <Badge tone={SENSITIVITY_TONE[doc.sensitivity]}>{SENSITIVITY_LABEL[doc.sensitivity]}</Badge>
                <span className="tabular-nums text-xs text-subtle-foreground">{formatDate(doc.ingested_at)}</span>

                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => onToggle(doc.id)}
                    aria-expanded={isOpen}
                    aria-controls={`chain-${doc.id}`}
                    className={rowAction}
                  >
                    <History className="size-3.5" aria-hidden="true" />
                    History
                    <ChevronDown
                      className={cn("size-3.5 transition-transform duration-(--duration-hover)", isOpen && "rotate-180")}
                      aria-hidden="true"
                    />
                  </button>
                  {/* Offered on every row, superseded ones included. The server refuses a
                      second supersession with a 409 naming what to do instead, and hiding
                      the action would leave a reader guessing why it is missing. */}
                  <button type="button" onClick={() => onRevise(doc)} className={rowAction}>
                    Revise
                  </button>
                </div>
              </div>

              {isOpen && (
                <div id={`chain-${doc.id}`} className="border-t border-border bg-surface-sunken/50 px-5 py-4">
                  <VersionChain document={doc} />
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
