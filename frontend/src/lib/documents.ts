import { apiGet, apiGetOrNull } from "@/lib/http";

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
};
