import type { Minutes } from "@/lib/minutes";

/**
 * Minutes fixtures for the frontend unit tests — the `mockMinutes` store that lived
 * in `lib/minutes.ts` until CP-C replaced it with a real client. Kept because the
 * assertions it supports are contract assertions: which version stands, and that a
 * draft correction supersedes a finalised record.
 *
 * **Not shipped.** Nothing under `src/` imports this.
 */

const WS = "00000000-0000-0000-0000-000000000001";

/**
 * Demo minutes for the fictional Meridian board.
 *
 * Scenario data, in the same category as the meetings, decisions and packs mocks
 * — a fictional company's paperwork, not a claim about anything Callosum
 * measured. The set is shaped to exercise every state the domain reaches: a
 * finalised record, a supersession pair, and a live draft.
 *
 * Bodies are deliberately plain prose. `minutes.body` is unstructured TEXT with
 * no schema behind it, so rendering anything richer than paragraphs would be
 * inventing a format the backend has never promised.
 */
export const MINUTES_FIXTURES: Minutes[] = [
  {
    id: "min-m14-v1",
    meeting_id: "m-14",
    body: [
      "The board reviewed the FY27 runway scenarios and adopted the middle case as the planning assumption.",
      "",
      "A six-person engineering hire was approved against the FY27 plan. A proposal to open a second office in Berlin was rejected on runway grounds; the board asked for it to be revisited only after the Series B closes.",
      "",
      "Pricing Model B was discussed at length and rejected for FY27. Marcus Webb's dissent was recorded.",
    ].join("\n"),
    status: "final",
    version_no: 1,
    superseded_by_id: null,
    finalised_at: "2026-07-09T17:30:00Z",
    version: 3,
    created_at: "2026-07-09T15:05:00Z",
    updated_at: "2026-07-09T17:30:00Z",
    workspace_id: WS,
  },
  {
    id: "min-q3-v1",
    meeting_id: "m-q3",
    body: [
      "The board reviewed the Q3 FY26 results against the KPI pack.",
      "",
      "The FY27 forecast revision was deferred pending the Q4 audit numbers; Priya Nair will bring a revised forecast to the next cycle.",
      "",
      "Series B final terms remain open. The preference stack is to be modelled before a vote is taken.",
    ].join("\n"),
    status: "final",
    version_no: 1,
    superseded_by_id: "min-q3-v2",
    finalised_at: "2026-07-21T16:00:00Z",
    version: 4,
    created_at: "2026-07-21T14:10:00Z",
    updated_at: "2026-07-22T10:15:00Z",
    workspace_id: WS,
  },
  {
    id: "min-q3-v2",
    meeting_id: "m-q3",
    body: [
      "The board reviewed the Q3 FY26 results against the KPI pack.",
      "",
      "The FY27 forecast revision was deferred pending the Q4 audit numbers; Priya Nair will bring a revised forecast to the next cycle.",
      "",
      "Series B final terms remain open. The preference stack is to be modelled before a vote is taken.",
      "",
      "Correction, recorded 22 July: the decision to adopt usage-based pricing was taken at this session and was omitted from the first record. Raj Malhotra confirmed the reversal of the FY27 position; Priya Nair asked that the migration plan be minuted.",
    ].join("\n"),
    status: "draft",
    version_no: 2,
    superseded_by_id: null,
    finalised_at: null,
    version: 2,
    created_at: "2026-07-22T10:15:00Z",
    updated_at: "2026-07-22T10:40:00Z",
    workspace_id: WS,
  },
  {
    id: "min-seq-v1",
    meeting_id: "m-seq",
    body: [
      "Sequoia confirmed they will lead the Series B at the proposed valuation.",
      "",
      "Terms are not yet final. The board took no vote on liquidation preference or board composition at this session.",
    ].join("\n"),
    status: "draft",
    version_no: 1,
    superseded_by_id: null,
    finalised_at: null,
    version: 1,
    created_at: "2026-07-19T11:30:00Z",
    updated_at: "2026-07-19T11:30:00Z",
    workspace_id: WS,
  },
];

