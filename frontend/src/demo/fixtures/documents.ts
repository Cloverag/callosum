import type { Document, QuarantineItem } from "@/lib/documents";
import { DEMO_WORKSPACE_ID, DOCUMENT, QUARANTINE } from "./ids";

/**
 * Eight documents spanning every `DocType` and the full sensitivity range.
 *
 * `SENSITIVITY_LABEL` has five levels and the clearance-filtering surfaces read
 * very differently at 0 and at 4, so both ends are present. Two of the eight
 * form a supersession chain (`DOCUMENT[2]` -> `DOCUMENT[3]`), which is what
 * `/documents`'s version-chain panel exists to render; a set where every
 * `superseded_by_id` is null would leave that panel permanently empty.
 */
export const DOCUMENTS: Document[] = [
  {
    id: DOCUMENT[0], title: "Q2 Board Deck", doc_type: "board_deck",
    source_uri: "s3://demo/q2-board-deck.pdf", sensitivity: 2,
    authored_at: "2026-07-08T00:00:00Z", ingested_at: "2026-07-09T10:12:00Z",
    revision: 1, superseded_by_id: null,
  },
  {
    id: DOCUMENT[1], title: "Q2 Meeting Transcript", doc_type: "transcript",
    source_uri: null, sensitivity: 3,
    authored_at: "2026-07-15T15:30:00Z", ingested_at: "2026-07-15T16:02:00Z",
    revision: 1, superseded_by_id: null,
  },
  {
    // Superseded — the head of the chain the version panel walks.
    id: DOCUMENT[2], title: "Series B Term Sheet", doc_type: "contract",
    source_uri: "s3://demo/term-sheet-v1.pdf", sensitivity: 4,
    authored_at: "2026-07-30T00:00:00Z", ingested_at: "2026-07-30T09:41:00Z",
    revision: 1, superseded_by_id: DOCUMENT[3],
  },
  {
    id: DOCUMENT[3], title: "Series B Term Sheet (revised)", doc_type: "contract",
    source_uri: "s3://demo/term-sheet-v2.pdf", sensitivity: 4,
    authored_at: "2026-08-04T00:00:00Z", ingested_at: "2026-08-04T18:22:00Z",
    revision: 2, superseded_by_id: null,
  },
  {
    id: DOCUMENT[4], title: "FY27 Operating Budget", doc_type: "memo",
    source_uri: null, sensitivity: 2,
    authored_at: "2026-06-28T00:00:00Z", ingested_at: "2026-06-29T08:00:00Z",
    revision: 1, superseded_by_id: null,
  },
  {
    id: DOCUMENT[5], title: "Investor update — August", doc_type: "email",
    source_uri: null, sensitivity: 1,
    authored_at: "2026-08-31T17:00:00Z", ingested_at: "2026-08-31T17:05:00Z",
    revision: 1, superseded_by_id: null,
  },
  {
    // Public, so the low end of the clearance filter is populated too.
    id: DOCUMENT[6], title: "Company overview (public)", doc_type: "memo",
    source_uri: "https://example.com/about", sensitivity: 0,
    authored_at: null, ingested_at: "2026-05-02T12:00:00Z",
    revision: 1, superseded_by_id: null,
  },
  {
    id: DOCUMENT[7], title: "Q2 Minutes (final)", doc_type: "minutes",
    source_uri: null, sensitivity: 2,
    authored_at: "2026-07-17T00:00:00Z", ingested_at: "2026-07-17T09:00:00Z",
    revision: 1, superseded_by_id: null,
  },
];

/**
 * Three rejected extractions, one per named `FAILURE_REASON_LABEL` key plus one
 * unrecognised reason.
 *
 * The unrecognised one is the point. `FailureReason` is `... | string`, so the
 * surface has to render a reason it has no label for, and a fixture set drawn
 * only from the four known keys would never make it do that.
 */
export const QUARANTINE_ITEMS: QuarantineItem[] = [
  {
    id: QUARANTINE[0], workspace_id: DEMO_WORKSPACE_ID, document_id: DOCUMENT[1],
    chunk_id: null, source: "Daniel Reyes", relation: "COMMITTED_TO",
    target: "Series B close by 30 September",
    quote: "we will have this closed before the end of the quarter",
    confidence: 0.71, reason: "quote_not_found",
    detail: "The quoted span does not occur in the chunk it was attributed to.",
    provider: "anthropic", extractor_model: "claude-sonnet-5",
    created_at: "2026-07-15T16:10:00Z",
  },
  {
    id: QUARANTINE[1], workspace_id: DEMO_WORKSPACE_ID, document_id: DOCUMENT[0],
    chunk_id: null, source: "Northwind Ventures", relation: "HOLDS_STAKE_IN",
    target: "Northwind Ventures",
    quote: "Northwind's position is unchanged",
    confidence: 0.88, reason: "self_reference",
    detail: "Source and target resolve to the same entity.",
    provider: "anthropic", extractor_model: "claude-sonnet-5",
    created_at: "2026-07-09T10:20:00Z",
  },
  {
    id: QUARANTINE[2], workspace_id: DEMO_WORKSPACE_ID, document_id: DOCUMENT[3],
    chunk_id: null, source: "Kestrel Capital", relation: "OBSERVES",
    target: "the audit committee",
    quote: "Kestrel will take an observer seat on audit",
    confidence: 0.44, reason: "confidence_below_floor",
    detail: "0.44 is under the 0.60 floor for CONTRACT-sourced relations.",
    provider: "anthropic", extractor_model: "claude-sonnet-5",
    created_at: "2026-08-04T18:31:00Z",
  },
];
