"use client";

import React, { useState, useEffect } from "react";
import {
  FileText,
  Upload,
  Shield,
  FileCheck,
  AlertTriangle,
  Search,
  Filter,
  Plus,
  RefreshCw,
  CheckCircle2,
  Lock,
  Layers,
  FileCode,
  X,
  FileUp,
} from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

interface DocumentItem {
  id: string;
  title: string;
  doc_type: string;
  source_uri: string | null;
  sensitivity: number;
  authored_at: string | null;
  ingested_at: string;
}

interface QuarantineItem {
  id: number;
  document_id: string | null;
  chunk_id: string | null;
  source: string;
  relation: string;
  target: string;
  quote: string;
  confidence: number;
  reason: string;
  detail: string;
  created_at: string;
}

const SENSITIVITY_LABELS: Record<number, { label: string; bg: string; text: string; border: string }> = {
  0: { label: "Public", bg: "bg-emerald-500/10", text: "text-emerald-400", border: "border-emerald-500/20" },
  1: { label: "Internal", bg: "bg-blue-500/10", text: "text-blue-400", border: "border-blue-500/20" },
  2: { label: "Confidential", bg: "bg-amber-500/10", text: "text-amber-400", border: "border-amber-500/20" },
  3: { label: "Executive", bg: "bg-purple-500/10", text: "text-purple-400", border: "border-purple-500/20" },
  4: { label: "Restricted", bg: "bg-rose-500/10", text: "text-rose-400", border: "border-rose-500/20" },
};

const DEMO_DOCUMENTS: DocumentItem[] = [
  {
    id: "d1010000-0000-0000-0000-000000000001",
    title: "Board Meeting 12 Transcript — Pricing Model B Rejection",
    doc_type: "transcript",
    source_uri: "board_meeting_12_transcript.txt",
    sensitivity: 1,
    authored_at: "2026-07-01T10:00:00Z",
    ingested_at: "2026-07-01T10:05:00Z",
  },
  {
    id: "d1020000-0000-0000-0000-000000000002",
    title: "Board Meeting 13 Transcript — Usage Pricing Reversal",
    doc_type: "transcript",
    source_uri: "board_meeting_13_transcript.txt",
    sensitivity: 2,
    authored_at: "2026-07-10T14:00:00Z",
    ingested_at: "2026-07-10T14:10:00Z",
  },
  {
    id: "d1030000-0000-0000-0000-000000000003",
    title: "FY27 Compensation & Governance Review",
    doc_type: "memo",
    source_uri: "compensation_review_CONFIDENTIAL.txt",
    sensitivity: 3,
    authored_at: "2026-07-15T09:00:00Z",
    ingested_at: "2026-07-15T09:12:00Z",
  },
];

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [quarantineItems, setQuarantineItems] = useState<QuarantineItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedType, setSelectedType] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [showQuarantineModal, setShowQuarantineModal] = useState(false);

  // Upload Modal State
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadDocType, setUploadDocType] = useState("transcript");
  const [uploadSensitivity, setUploadSensitivity] = useState(2);
  const [uploadText, setUploadText] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);

  const fetchDocuments = async () => {
    setLoading(true);
    try {
      const docs = await apiClient.listDocuments();
      const quars = await apiClient.getQuarantine();
      setDocuments(docs.length > 0 ? docs : DEMO_DOCUMENTS);
      setQuarantineItems(quars);
    } catch {
      setDocuments(DEMO_DOCUMENTS);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  const handleIntakeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setUploading(true);
    setUploadError(null);
    setUploadSuccess(null);

    try {
      if (selectedFile) {
        const formData = new FormData();
        formData.append("file", selectedFile);
        if (uploadTitle) formData.append("title", uploadTitle);
        formData.append("doc_type", uploadDocType);
        formData.append("sensitivity", uploadSensitivity.toString());

        const newDoc = await apiClient.uploadDocument(formData);
        setUploadSuccess(`Successfully uploaded "${newDoc.title}"!`);
      } else if (uploadText.trim()) {
        const newDoc = await apiClient.intakeDocument({
          title: uploadTitle || "Untitled Intake Document",
          doc_type: uploadDocType,
          raw_text: uploadText,
          sensitivity: uploadSensitivity,
        });
        setUploadSuccess(`Successfully ingested "${newDoc.title}"!`);
      } else {
        setUploadError("Please provide raw text or select a file to upload.");
        setUploading(false);
        return;
      }

      await fetchDocuments();
      setTimeout(() => {
        setShowUploadModal(false);
        setUploadTitle("");
        setUploadText("");
        setSelectedFile(null);
        setUploadSuccess(null);
      }, 1200);
    } catch (err: any) {
      setUploadError(err.message || "Failed to intake document.");
    } finally {
      setUploading(false);
    }
  };

  const filteredDocs = documents.filter((doc) => {
    const matchesType = selectedType === "all" || doc.doc_type.toLowerCase() === selectedType;
    const matchesQuery =
      doc.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      doc.doc_type.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesType && matchesQuery;
  });

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header Bar */}
      <PageHeader
        title="Source Documents & Intake"
        description="Tenant-isolated source repository with automated chunking, deduplication, and clearance governance."
        icon={<FileText className="text-blue-500" />}
      />

      {/* Metrics Bar */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="p-4 flex items-center gap-4 bg-surface-raised border border-border">
          <div className="p-3 rounded-xl bg-blue-500/10 text-blue-500">
            <Layers className="size-5" />
          </div>
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Indexed Documents</p>
            <p className="text-xl font-bold text-foreground">{documents.length}</p>
          </div>
        </Card>

        <Card className="p-4 flex items-center gap-4 bg-surface-raised border border-border">
          <div className="p-3 rounded-xl bg-amber-500/10 text-amber-500">
            <AlertTriangle className="size-5" />
          </div>
          <div className="flex-1">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Quarantine Queue</p>
            <div className="flex items-center justify-between">
              <p className="text-xl font-bold text-foreground">{quarantineItems.length}</p>
              {quarantineItems.length > 0 && (
                <button
                  onClick={() => setShowQuarantineModal(true)}
                  className="text-xs text-amber-500 hover:underline font-medium"
                >
                  Review
                </button>
              )}
            </div>
          </div>
        </Card>

        <Card className="p-4 flex items-center gap-4 bg-surface-raised border border-border">
          <div className="p-3 rounded-xl bg-emerald-500/10 text-emerald-500">
            <Shield className="size-5" />
          </div>
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Clearance Scope</p>
            <p className="text-xl font-bold text-foreground">Level 4 (Restricted)</p>
          </div>
        </Card>

        <Card className="p-4 flex items-center gap-4 bg-surface-raised border border-border">
          <div className="p-3 rounded-xl bg-purple-500/10 text-purple-500">
            <FileCheck className="size-5" />
          </div>
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Deduplication</p>
            <p className="text-xl font-bold text-foreground">SHA-256 Active</p>
          </div>
        </Card>
      </div>

      {/* Action Controls & Filters */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-3 w-full sm:w-auto">
          {/* Search Bar */}
          <div className="relative flex-1 sm:w-72">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search documents..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-4 py-2 text-sm rounded-xl border border-border bg-surface-raised text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-blue-500/50"
            />
          </div>

          {/* Type Filter */}
          <select
            value={selectedType}
            onChange={(e) => setSelectedType(e.target.value)}
            className="px-3 py-2 text-sm rounded-xl border border-border bg-surface-raised text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500/50"
          >
            <option value="all">All Formats</option>
            <option value="transcript">Transcript</option>
            <option value="memo">Memo</option>
            <option value="deck">Deck</option>
            <option value="minutes">Minutes</option>
          </select>
        </div>

        <div className="flex items-center gap-3">
          <Button variant="secondary" onClick={fetchDocuments} className="rounded-xl">
            <RefreshCw className="size-4" />
            Refresh
          </Button>
          <Button onClick={() => setShowUploadModal(true)} className="rounded-xl bg-blue-600 hover:bg-blue-700 text-white">
            <Plus className="size-4" />
            Intake Document
          </Button>
        </div>
      </div>

      {/* Documents Table */}
      <Card className="overflow-hidden border border-border bg-surface-raised rounded-2xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-surface-sunken/50 text-xs uppercase text-muted-foreground border-b border-border">
              <tr>
                <th className="px-6 py-3 font-semibold">Document Title</th>
                <th className="px-6 py-3 font-semibold">Type</th>
                <th className="px-6 py-3 font-semibold">Sensitivity</th>
                <th className="px-6 py-3 font-semibold">Source File</th>
                <th className="px-6 py-3 font-semibold">Ingested Date</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {loading ? (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center text-muted-foreground">
                    Loading indexed documents...
                  </td>
                </tr>
              ) : filteredDocs.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center text-muted-foreground">
                    No documents found matching your filter criteria.
                  </td>
                </tr>
              ) : (
                filteredDocs.map((doc) => {
                  const sens = SENSITIVITY_LABELS[doc.sensitivity] || SENSITIVITY_LABELS[2];
                  return (
                    <tr key={doc.id} className="hover:bg-surface-sunken/30 transition-colors">
                      <td className="px-6 py-4 font-medium text-foreground flex items-center gap-3">
                        <FileText className="size-4 text-blue-500 shrink-0" />
                        <span>{doc.title}</span>
                      </td>
                      <td className="px-6 py-4">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-surface-sunken text-muted-foreground border border-border uppercase tracking-wider">
                          {doc.doc_type}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <span
                          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold ${sens.bg} ${sens.text} ${sens.border} border`}
                        >
                          <Lock className="size-3" />
                          {sens.label} (L{doc.sensitivity})
                        </span>
                      </td>
                      <td className="px-6 py-4 font-mono text-xs text-muted-foreground">
                        {doc.source_uri || "—"}
                      </td>
                      <td className="px-6 py-4 text-xs text-muted-foreground">
                        {new Date(doc.ingested_at).toLocaleDateString("en-US", {
                          month: "short",
                          day: "numeric",
                          year: "numeric",
                        })}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Intake / Upload Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <Card className="w-full max-w-xl p-6 bg-surface-raised border border-border rounded-2xl shadow-2xl space-y-5 relative">
            <button
              onClick={() => setShowUploadModal(false)}
              className="absolute right-4 top-4 text-muted-foreground hover:text-foreground"
            >
              <X className="size-5" />
            </button>

            <div className="flex items-center gap-3">
              <div className="p-3 rounded-xl bg-blue-500/10 text-blue-500">
                <FileUp className="size-6" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-foreground">Intake Source Document</h3>
                <p className="text-xs text-muted-foreground">
                  Ingest board material with automatic chunking, deduplication, and clearance controls.
                </p>
              </div>
            </div>

            {uploadError && (
              <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
                {uploadError}
              </div>
            )}

            {uploadSuccess && (
              <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs flex items-center gap-2">
                <CheckCircle2 className="size-4" />
                {uploadSuccess}
              </div>
            )}

            <form onSubmit={handleIntakeSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold uppercase text-muted-foreground mb-1">
                  Document Title
                </label>
                <input
                  type="text"
                  placeholder="e.g. Board Meeting 14 Executive Summary"
                  value={uploadTitle}
                  onChange={(e) => setUploadTitle(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-xl border border-border bg-surface-sunken text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold uppercase text-muted-foreground mb-1">
                    Document Type
                  </label>
                  <select
                    value={uploadDocType}
                    onChange={(e) => setUploadDocType(e.target.value)}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-border bg-surface-sunken text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                  >
                    <option value="transcript">Transcript</option>
                    <option value="memo">Memo</option>
                    <option value="deck">Deck</option>
                    <option value="minutes">Minutes</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold uppercase text-muted-foreground mb-1">
                    Sensitivity Level
                  </label>
                  <select
                    value={uploadSensitivity}
                    onChange={(e) => setUploadSensitivity(Number(e.target.value))}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-border bg-surface-sunken text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                  >
                    <option value={0}>0 — Public</option>
                    <option value={1}>1 — Internal</option>
                    <option value={2}>2 — Confidential</option>
                    <option value={3}>3 — Executive</option>
                    <option value={4}>4 — Restricted</option>
                  </select>
                </div>
              </div>

              {/* Upload Option 1: File Upload */}
              <div>
                <label className="block text-xs font-semibold uppercase text-muted-foreground mb-1">
                  Upload File (PDF, DOCX, TXT, VTT, MD)
                </label>
                <input
                  type="file"
                  accept=".pdf,.docx,.txt,.vtt,.md"
                  onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                  className="w-full px-3 py-2 text-xs text-muted-foreground rounded-xl border border-border bg-surface-sunken file:mr-4 file:py-1 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-blue-600 file:text-white hover:file:bg-blue-700 cursor-pointer"
                />
              </div>

              {/* Upload Option 2: Raw Text Input */}
              <div>
                <label className="block text-xs font-semibold uppercase text-muted-foreground mb-1">
                  Or Paste Raw Text / Transcript
                </label>
                <textarea
                  rows={4}
                  placeholder="Paste transcript or raw document text here..."
                  value={uploadText}
                  onChange={(e) => setUploadText(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono rounded-xl border border-border bg-surface-sunken text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <Button type="button" variant="outline" onClick={() => setShowUploadModal(false)} className="rounded-xl">
                  Cancel
                </Button>
                <Button type="submit" disabled={uploading} className="rounded-xl bg-blue-600 hover:bg-blue-700 text-white">
                  {uploading ? "Ingesting..." : "Complete Intake"}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}

      {/* Quarantine Review Modal */}
      {showQuarantineModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <Card className="w-full max-w-3xl p-6 bg-surface-raised border border-border rounded-2xl shadow-2xl space-y-4 relative max-h-[85vh] overflow-hidden flex flex-col">
            <button
              onClick={() => setShowQuarantineModal(false)}
              className="absolute right-4 top-4 text-muted-foreground hover:text-foreground"
            >
              <X className="size-5" />
            </button>

            <div className="flex items-center gap-3">
              <div className="p-3 rounded-xl bg-amber-500/10 text-amber-500">
                <AlertTriangle className="size-6" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-foreground">Extraction Quarantine Queue</h3>
                <p className="text-xs text-muted-foreground">
                  Unverified quotes or rejected extractions held for human safety audit.
                </p>
              </div>
            </div>

            <div className="overflow-y-auto flex-1 divide-y divide-border border border-border rounded-xl">
              {quarantineItems.length === 0 ? (
                <div className="p-8 text-center text-sm text-muted-foreground">
                  No quarantine items found. All extractions verified clean!
                </div>
              ) : (
                quarantineItems.map((q) => (
                  <div key={q.id} className="p-4 space-y-2 hover:bg-surface-sunken/40">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-amber-400 uppercase tracking-wider">{q.reason}</span>
                      <span className="text-muted-foreground">{new Date(q.created_at).toLocaleString()}</span>
                    </div>
                    <p className="text-sm font-medium text-foreground">
                      {q.source} <span className="text-blue-400 font-mono">[{q.relation}]</span> {q.target}
                    </p>
                    <p className="text-xs font-mono bg-surface-sunken p-2.5 rounded-lg border border-border text-muted-foreground">
                      "{q.quote || q.detail}"
                    </p>
                  </div>
                ))
              )}
            </div>

            <div className="flex justify-end pt-2">
              <Button onClick={() => setShowQuarantineModal(false)} variant="outline" className="rounded-xl">
                Close Queue
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
