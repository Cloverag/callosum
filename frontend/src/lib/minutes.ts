import type { BadgeTone } from "@/components/ui/badge";

/**
 * Meeting minutes — the record of what a meeting actually resolved.
 *
 * Like `decisions.ts` and `packs.ts`, this mirrors a backend contract that
 * EXISTS: `meridian/minutes.py` and migration `0010_board_pack`, merged in
 * PR #33. Field names are snake_case and match the Python dataclass one for one,
 * so wiring this to the real API at P3 is a swap of the `minutesApi` object and
 * nothing else.
 *
 * Where this file and `meridian/minutes.py` disagree, the Python is right.
 *
 * ---------------------------------------------------------------------------
 * MINUTES ARE NOT CLEARANCE-FILTERED, AND THIS FILE MUST NOT PRETEND THEY ARE
 * ---------------------------------------------------------------------------
 *
 * `board_pack_item` is filtered by document sensitivity before it reaches the
 * caller. `minutes` is not. The table has no `sensitivity` column, and no
 * function in `meridian/minutes.py` takes a `clearance` argument — the only
 * scoping is `workspace_id` through RLS.
 *
 * So this surface carries no clearance parameter and shows no access-level
 * notice. Adding either would be a lie in the more dangerous direction: it would
 * tell a reader that the body they are looking at has been filtered for them
 * when nothing filtered it, and would suggest the product enforces a boundary it
 * does not currently enforce.
 *
 * Whether it *should* be filtered is a real question — minutes of a session that
 * discussed compensation or a termination are readable by any workspace member
 * today. That is raised as a backend question, not patched here. The frontend's
 * job is to mirror the contract as it is.
 */

// --- Status ----------------------------------------------------------------

/** `meridian/minutes.py:23-26`. Minutes are draft or final; there is no third state. */
export type MinutesStatus = "draft" | "final";

export const MINUTES_STATUS_LABEL: Record<MinutesStatus, string> = {
  draft: "Draft",
  final: "Final",
};

export const MINUTES_STATUS_TONE: Record<MinutesStatus, BadgeTone> = {
  draft: "neutral",
  final: "success",
};

export const MINUTES_STATUS_DOT: Record<MinutesStatus, string> = {
  draft: "bg-muted-foreground",
  final: "bg-success",
};

export const MINUTES_STATUSES = Object.keys(MINUTES_STATUS_LABEL) as MinutesStatus[];

/**
 * Meeting statuses that lock minutes against mutation, from
 * `_LOCKED_MEETING_STATUSES` (`meridian/minutes.py:29`).
 *
 * This is very nearly the *inverse* of the board-pack lock set, and the
 * asymmetry is correct rather than an oversight: a pack is prepared before a
 * meeting and freezes when it starts, while minutes are written during or after
 * one and cannot exist before it. `cancelled` is the single status that locks
 * both — a meeting that never happened has neither a valid pre-read nor a record.
 *
 * Declared as a plain string set rather than reusing `MeetingStatus` from
 * `lib/meetings.ts` for the same reason `packs.ts` does: that mock declares
 * `review` and `archived`, which `meridian/meetings.py` has never had, and omits
 * `cancelled`, which it does have. See issue #47.
 */
export const MINUTES_LOCKED_MEETING_STATUSES: ReadonlySet<string> = new Set([
  "draft",
  "scheduled",
  "cancelled",
]);

// --- Read model ------------------------------------------------------------

/** Mirrors the `Minutes` dataclass (`meridian/minutes.py:62-74`). */
export type Minutes = {
  id: string;
  meeting_id: string;
  /** Free text. The domain imposes no structure beyond "not empty". */
  body: string;
  status: MinutesStatus;
  /** Published-artifact lineage. Distinct from `version` — see CONTRIBUTING.md. */
  version_no: number;
  /** Set when this record was replaced; points at its replacement. */
  superseded_by_id: string | null;
  finalised_at: string | null; // ISO
  /** Optimistic-concurrency counter, not a published-version number. */
  version: number;
  created_at: string; // ISO
  updated_at: string; // ISO
  workspace_id: string;
};

// --- Derived helpers -------------------------------------------------------

/**
 * True when the record can still be edited.
 *
 * Mirrors the two guards every mutating operation in `minutes.py` applies: the
 * record must be `draft`, and the parent meeting must not be in a locked status.
 * A hint for disabling controls, not an authorisation check — the server
 * enforces both regardless of what the UI renders.
 */
export function isEditable(minutes: Minutes, meetingStatus: string | undefined): boolean {
  if (minutes.status !== "draft") return false;
  if (meetingStatus === undefined) return false;
  return !MINUTES_LOCKED_MEETING_STATUSES.has(meetingStatus);
}

/**
 * Follows `superseded_by_id` to the record that replaced this one.
 *
 * Returns `null` rather than throwing when the target is absent, matching
 * `supersededBy` in `decisions.ts` and `packs.ts`.
 */
export function supersededBy(minutes: Minutes, all: Minutes[]): Minutes | null {
  if (!minutes.superseded_by_id) return null;
  return all.find((m) => m.id === minutes.superseded_by_id) ?? null;
}

/**
 * The record that currently stands for a meeting, or `null` if it has none.
 *
 * "Stands" means: highest `version_no` that has not been superseded. A meeting
 * can hold several records — a finalised set plus the draft that will replace
 * it — and only one of them is the one a reader should treat as current.
 */
export function current(all: Minutes[], meetingId: string): Minutes | null {
  const forMeeting = all.filter((m) => m.meeting_id === meetingId && !m.superseded_by_id);
  if (forMeeting.length === 0) return null;
  return forMeeting.reduce((best, m) => (m.version_no > best.version_no ? m : best));
}

// --- Mock store ------------------------------------------------------------

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
const mockMinutes: Minutes[] = [
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

const clone = (m: Minutes): Minutes => structuredClone(m);
const delay = (ms = 400) => new Promise((r) => setTimeout(r, ms));

/**
 * Mocked Meridian minutes API.
 *
 * Method names and arguments follow `meridian/minutes.py` so the P3 swap is
 * mechanical. There is no `clearance` argument, because the Python has none.
 *
 * Ordering matches `list_minutes`: `version_no DESC, created_at DESC`.
 */
export const minutesApi = {
  async list(opts?: { meeting_id?: string; status?: MinutesStatus }): Promise<Minutes[]> {
    await delay();
    return mockMinutes
      .filter((m) => (opts?.meeting_id ? m.meeting_id === opts.meeting_id : true))
      .filter((m) => (opts?.status ? m.status === opts.status : true))
      .slice()
      .sort(
        (a, b) =>
          b.version_no - a.version_no || b.created_at.localeCompare(a.created_at),
      )
      .map(clone);
  },

  async get(id: string): Promise<Minutes | null> {
    await delay(200);
    const m = mockMinutes.find((x) => x.id === id);
    return m ? clone(m) : null;
  },
};
