import { apiGet, apiGetOrNull, apiPost } from "@/lib/http";

/**
 * Documents — the readable columns of the core `document` table.
 *
 * This is not a mock of the Documents *page*; it exists because
 * `board_pack_item` carries a `document_id` and nothing else. The pack contract
 * (`meridian/packs.py`) deliberately does not denormalise a title onto the item,
 * so any surface that renders a pack has to resolve documents separately — and
 * needs a shape to resolve them into.
 *
 * Columns mirror `schema/postgres.sql:51-63`. Only the fields a reader can
 * legitimately see are modelled: `raw_text`, `content_hash`, and `metadata` are
 * omitted because no board surface should be handing them to a browser.
 *
 * `document` is part of the FROZEN core schema. If this file and
 * `schema/postgres.sql` disagree, the SQL is right.
 */

/** `schema/postgres.sql:54`. */
export type DocType =
  | "board_deck"
  | "transcript"
  | "email"
  | "memo"
  | "contract"
  | "minutes";

export const DOC_TYPE_LABEL: Record<DocType, string> = {
  board_deck: "Board deck",
  transcript: "Transcript",
  email: "Email",
  memo: "Memo",
  contract: "Contract",
  minutes: "Minutes",
};

/**
 * The clearance ladder, from the `sensitivity` lookup table seeded by
 * `schema/postgres.sql:15-24` and mirrored in `meridian/packs.py:33-37`.
 *
 * A caller's clearance admits every document at or below their level. Keep this
 * in step with the table: a hard-coded maximum silently stops meaning "maximum"
 * the moment a level is added.
 */
// The clearance *ladder* deliberately does not live here any more. It moved to the
// server with CP-E: the API resolves a caller's clearance from their membership, so no
// client code has a legitimate use for the numbers. A `RESTRICTED_CLEARANCE = 4` left
// lying in the browser is an invitation to pass it somewhere, which is exactly the
// fail-open `clearance: int = 4` that `packs.list_packs` shipped with.
//
// `Sensitivity` stays, because a document's own level is data the caller may see and
// `SENSITIVITY_LABEL` renders it.

export type Sensitivity = 0 | 1 | 2 | 3 | 4;

export const SENSITIVITY_LABEL: Record<Sensitivity, string> = {
  0: "Public",
  1: "Investor",
  2: "Internal",
  3: "Confidential",
  4: "Restricted",
};

/** Mirrors the readable columns of `document`. */
export type Document = {
  id: string;
  title: string;
  doc_type: DocType;
  source_uri: string | null;
  sensitivity: Sensitivity;
  authored_at: string | null; // ISO — when written, not when ingested
  ingested_at: string; // ISO
};

// --- Mock store ------------------------------------------------------------

/**
 * Demo documents for the fictional Meridian board.
 *
 * Scenario data, in the same category as the meetings and decisions mocks — a
 * fictional company's paperwork, not a claim about anything Callosum measured.
 * The sensitivity spread is the point: it is what gives the board-pack surface
 * something real to withhold.
 */


// --- Intake ----------------------------------------------------------------

/**
 * The sensitivity levels intake accepts.
 *
 * **Four, not five.** `4 restricted` exists in the ladder and is deliberately not
 * creatable through intake — reserved pending the policy in #143 (who may create
 * restricted documents, whether founder-only is a role or a clearance, what audit it
 * carries). `SENSITIVITY_LABEL` still carries all five, because a document *filed*
 * elsewhere at level 4 must still render its label when a founder reads the list.
 */
export const INTAKE_SENSITIVITIES: readonly Sensitivity[] = [0, 1, 2, 3];

/**
 * What intake sends.
 *
 * `sensitivity` is REQUIRED and has no default here, mirroring the API. It used to
 * default to `0` — *public* — server-side, so a caller who said nothing published the
 * document at the widest visibility in the system. A default on the client would
 * reintroduce exactly that, one layer up: the form would submit a classification the
 * user never chose. See #143.
 */
export type IntakeRequest = {
  title: string;
  doc_type: DocType;
  raw_text: string;
  sensitivity: Sensitivity;
  source_uri?: string | null;
};

/** Why the evidence verifier refused an edge — `callosum.ontology.FailureReason`. */
export type FailureReason =
  | "quote_not_found"
  | "quote_empty"
  | "entity_not_extracted"
  | "self_reference"
  | string;

/**
 * Plain-language failure reasons. A director reading the quarantine queue is not
 * expected to know what `entity_not_extracted` means, and the raw enum is the kind of
 * label that makes a real safety mechanism look like a malfunction.
 */
export const FAILURE_REASON_LABEL: Record<string, string> = {
  quote_not_found: "Quote not found in the source",
  quote_empty: "No evidence quote offered",
  entity_not_extracted: "Referenced something never extracted",
  self_reference: "Linked a thing to itself",
};

/**
 * A rejected extraction, kept rather than deleted.
 *
 * Mirrors `QuarantineResponse` in `meridian/api/documents.py`. The quote is the point:
 * quarantine is not an error log, it is the record of what the verifier refused and
 * why, and a count alone would be a summary of exactly the thing this product exists
 * not to summarise.
 */
export type QuarantineItem = {
  id: string;
  workspace_id: string;
  document_id: string | null;
  chunk_id: string | null;
  source: string;
  relation: string;
  target: string;
  quote: string;
  confidence: number;
  reason: FailureReason;
  detail: string;
  provider: string;
  extractor_model: string;
  created_at: string; // ISO
};

// --- API client ------------------------------------------------------------

/**
 * Meridian documents API. **Live as of CP-E; the in-memory mock is gone.**
 *
 * It had to go. `packsApi` went live in CP-C while this stayed mocked, so the packs
 * page joined real `board_pack_item.document_id` values against fabricated ids. Every
 * item in every pack resolved to nothing and rendered "Document reference could not be
 * resolved" — a live surface making a false statement about real data.
 *
 * **`clearance` is no longer an argument, and that is the point.** The mock took one
 * because it filtered its own array; the real API resolves it from the caller's active
 * membership on every request (ADR-013). A client able to name its own clearance could
 * ask for every restricted document in the workspace, so there is deliberately nowhere
 * to pass one.
 */
export const documentsApi = {
  async list(opts?: { doc_type?: DocType }): Promise<Document[]> {
    return apiGet<Document[]>("/documents", { doc_type: opts?.doc_type });
  },

  /**
   * One document, or `null` when it does not exist **or** is above the caller's
   * clearance. The API answers 404 to both so the lookup cannot be used to prove a
   * restricted document exists, and `apiGetOrNull` preserves that here.
   */
  async get(id: string): Promise<Document | null> {
    return apiGetOrNull<Document>(`/documents/${encodeURIComponent(id)}`);
  },

  /**
   * File a source document.
   *
   * **The clearance ceiling is not checked here, and cannot be.** `/auth/me`
   * deliberately does not return the caller's clearance — it is per-workspace and
   * resolved per request, so reporting it from a session read would be reporting a
   * cached authorization. The client therefore offers every level intake accepts and
   * lets the server refuse: a 403 carries the level the caller may actually use.
   *
   * That is the right shape rather than a limitation. A filtered list would be a
   * convenience the server must not trust anyway, and building one would need an
   * endpoint that publishes clearance to the browser.
   */
  async intake(req: IntakeRequest): Promise<Document> {
    return apiPost<Document>("/documents/intake", req);
  },

  /**
   * Rejected extractions, at the caller's clearance.
   *
   * A clearance-filtered surface exactly like the document list, not an internal
   * diagnostic — a quarantined quote is a verbatim span of a source document, so it
   * carries the sensitivity of whatever it was quoted from.
   */
  async quarantine(): Promise<QuarantineItem[]> {
    return apiGet<QuarantineItem[]>("/documents/quarantine");
  },
};
