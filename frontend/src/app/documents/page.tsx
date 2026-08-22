"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { FileText, Upload } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { LoadFailed, asApiError } from "@/components/ui/load-failed";
import type { ApiError } from "@/lib/http";
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

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[] | null>(null);
  const [quarantine, setQuarantine] = useState<QuarantineItem[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [intakeOpen, setIntakeOpen] = useState(false);
  const [tab, setTab] = useState<"documents" | "quarantine">("documents");

  const load = useCallback(() => {
    documentsApi.list().then(setDocuments).catch((e) => setError(asApiError(e)));
    // Quarantine failing must not blank the document list — they are separate
    // reads and a reader can act on one without the other.
    documentsApi.quarantine().then(setQuarantine).catch(() => setQuarantine([]));
  }, []);

  useEffect(load, [load]);

  const onIngested = useCallback((doc: Document) => {
    setDocuments((prev) => (prev ? [doc, ...prev] : [doc]));
    // Extraction runs during intake, so a new document can add quarantine rows.
    documentsApi.quarantine().then(setQuarantine).catch(() => undefined);
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
          <DocumentList documents={documents} onIngest={() => setIntakeOpen(true)} />
        ) : (
          <QuarantineList items={quarantine} />
        )}
      </div>

      <IntakeDialog open={intakeOpen} onClose={() => setIntakeOpen(false)} onIngested={onIngested} />
    </div>
  );
}

function DocumentList({ documents, onIngest }: { documents: Document[] | null; onIngest: () => void }) {
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
        <h3 className="mt-3 text-sm font-medium text-foreground">No documents yet</h3>
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
        {documents.map((doc) => (
          <li key={doc.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3.5">
            <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">{doc.title}</span>
            <span className="text-xs text-muted-foreground">{DOC_TYPE_LABEL[doc.doc_type as DocType] ?? doc.doc_type}</span>
            <Badge tone={SENSITIVITY_TONE[doc.sensitivity]}>{SENSITIVITY_LABEL[doc.sensitivity]}</Badge>
            <span className="tabular-nums text-xs text-subtle-foreground">{formatDate(doc.ingested_at)}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
