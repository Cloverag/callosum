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
export const PUBLIC_CLEARANCE = 0;
export const INVESTOR_CLEARANCE = 1;
export const INTERNAL_CLEARANCE = 2;
export const CONFIDENTIAL_CLEARANCE = 3;
export const RESTRICTED_CLEARANCE = 4;

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
const mockDocuments: Document[] = [
  {
    id: "doc-q3-deck",
    title: "Q3 FY26 board deck",
    doc_type: "board_deck",
    source_uri: "gdrive://meridian/board/q3-fy26-deck.pdf",
    sensitivity: 1,
    authored_at: "2026-07-05T09:00:00Z",
    ingested_at: "2026-07-05T14:22:00Z",
  },
  {
    id: "doc-kpi",
    title: "FY27 KPI pack",
    doc_type: "board_deck",
    source_uri: "gdrive://meridian/board/fy27-kpis.xlsx",
    sensitivity: 1,
    authored_at: "2026-07-06T11:30:00Z",
    ingested_at: "2026-07-06T12:02:00Z",
  },
  {
    id: "doc-pricing-memo",
    title: "Pricing Model B — analysis",
    doc_type: "memo",
    source_uri: null,
    sensitivity: 2,
    authored_at: "2026-07-07T16:45:00Z",
    ingested_at: "2026-07-07T17:10:00Z",
  },
  {
    id: "doc-runway",
    title: "Runway and burn scenarios",
    doc_type: "memo",
    source_uri: null,
    sensitivity: 2,
    authored_at: "2026-07-08T10:15:00Z",
    ingested_at: "2026-07-08T10:40:00Z",
  },
  {
    id: "doc-seriesb-term",
    title: "Series B term sheet (draft)",
    doc_type: "contract",
    source_uri: "gdrive://meridian/legal/series-b-ts-v4.pdf",
    sensitivity: 3,
    authored_at: "2026-07-12T13:00:00Z",
    ingested_at: "2026-07-12T13:35:00Z",
  },
  {
    id: "doc-comp",
    title: "Executive compensation review",
    doc_type: "memo",
    source_uri: null,
    sensitivity: 4,
    authored_at: "2026-07-10T08:00:00Z",
    ingested_at: "2026-07-10T08:30:00Z",
  },
  {
    id: "doc-m14-minutes",
    title: "Board Meeting 14 — minutes",
    doc_type: "minutes",
    source_uri: null,
    sensitivity: 1,
    authored_at: "2026-07-09T15:00:00Z",
    ingested_at: "2026-07-09T15:20:00Z",
  },
  {
    id: "doc-hiring",
    title: "FY27 hiring plan",
    doc_type: "memo",
    source_uri: null,
    sensitivity: 2,
    authored_at: "2026-07-04T09:45:00Z",
    ingested_at: "2026-07-04T10:00:00Z",
  },
];

/**
 * The document store as the server sees it — every row, unfiltered.
 *
 * Exported for the mock pack API only, which applies the clearance predicate the
 * way `_fetch_items_for_packs` does. UI code must not import this: reading it
 * from a component is precisely the app-side filtering that Invariant #1 exists
 * to prevent.
 *
 * @internal
 */
export const __unfilteredDocuments = mockDocuments;

const clone = (d: Document): Document => structuredClone(d);
const delay = (ms = 300) => new Promise((r) => setTimeout(r, ms));

/**
 * Mocked document reads.
 *
 * Every method takes a `clearance` and filters before returning, mirroring the
 * server contract: a document above the caller's level is not returned in a
 * redacted form, it is not returned at all.
 */
export const documentsApi = {
  async list(opts: { clearance: number }): Promise<Document[]> {
    await delay();
    return mockDocuments
      .filter((d) => d.sensitivity <= opts.clearance)
      .slice()
      .sort((a, b) => b.ingested_at.localeCompare(a.ingested_at))
      .map(clone);
  },

  async get(id: string, opts: { clearance: number }): Promise<Document | null> {
    await delay(150);
    const d = mockDocuments.find((x) => x.id === id);
    // A document the caller cannot read is indistinguishable from one that does
    // not exist. Returning a different result for the two cases would turn this
    // lookup into an existence oracle.
    if (!d || d.sensitivity > opts.clearance) return null;
    return clone(d);
  },
};
