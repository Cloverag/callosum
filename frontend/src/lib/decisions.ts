import type { BadgeTone } from "@/components/ui/badge";

/**
 * Decisions and director stances.
 *
 * Unlike the other mocks in this directory, this file mirrors a backend contract
 * that EXISTS: `meridian/decisions.py` and migration `0009_decision`, merged in
 * PR #22 with 20 integration tests behind it. Field names are snake_case and
 * match the Python dataclasses one for one, so wiring this to the real API at P3
 * is a swap of the `decisionsApi` object and nothing else.
 *
 * Where this file and `meridian/decisions.py` disagree, the Python is right.
 * Do not add a status, a stance, or a transition here that the backend cannot
 * produce — the dashboard previously carried a `"pending"` decision status that
 * has never existed in the domain, which is how a mock stops being a preview of
 * the product and starts being fiction about it.
 */

// --- Status ----------------------------------------------------------------

/** `meridian/decisions.py:25-29`. There is no "pending"; a new decision is `proposed`. */
import { apiGet, apiGetOrNull } from "@/lib/http";

export type DecisionStatus =
  | "proposed"
  | "approved"
  | "rejected"
  | "superseded"
  | "deferred";

export const DECISION_STATUS_LABEL: Record<DecisionStatus, string> = {
  proposed: "Proposed",
  approved: "Approved",
  rejected: "Rejected",
  superseded: "Superseded",
  deferred: "Deferred",
};

export const DECISION_STATUS_TONE: Record<DecisionStatus, BadgeTone> = {
  proposed: "info",
  approved: "success",
  rejected: "danger",
  superseded: "neutral",
  deferred: "warning",
};

export const DECISION_STATUS_DOT: Record<DecisionStatus, string> = {
  proposed: "bg-info",
  approved: "bg-success",
  rejected: "bg-danger",
  superseded: "bg-subtle-foreground",
  deferred: "bg-warning",
};

export const DECISION_STATUSES = Object.keys(DECISION_STATUS_LABEL) as DecisionStatus[];

/**
 * The domain state machine, copied from `_ALLOWED_TRANSITIONS`.
 *
 * Four of the five states are terminal. `approved` is terminal here because its
 * only exit is `supersede_decision()`, which creates a *new* decision rather than
 * mutating this one — that is what keeps an approved decision immutable.
 *
 * `deferred` is terminal by design (owner decision, 2026-07-27): a deferred motion
 * closes as deferred, and re-examination creates a new motion referencing it, so
 * the minutes and voting record of the meeting that deferred it stay intact.
 */
export const DECISION_TRANSITIONS: Record<DecisionStatus, DecisionStatus[]> = {
  proposed: ["approved", "rejected", "deferred"],
  approved: [],
  rejected: [],
  superseded: [],
  deferred: [],
};

/** True when the only way forward is a new decision record. */
export function isTerminal(status: DecisionStatus): boolean {
  return DECISION_TRANSITIONS[status].length === 0;
}

// --- Stances ---------------------------------------------------------------

/** `meridian/decisions.py:41-46`. Uppercase in the domain; do not lowercase them. */
export type Stance = "SUPPORTED" | "OPPOSED" | "APPROVED" | "REQUESTED";

export const STANCE_LABEL: Record<Stance, string> = {
  SUPPORTED: "Supported",
  OPPOSED: "Opposed",
  APPROVED: "Approved",
  REQUESTED: "Requested changes",
};

export const STANCE_TONE: Record<Stance, BadgeTone> = {
  SUPPORTED: "success",
  OPPOSED: "danger",
  APPROVED: "accent",
  REQUESTED: "warning",
};

/**
 * Display order for a stance breakdown. Deliberately not alphabetical: this reads
 * as a spectrum from assent to dissent, so the shape of a board's position is
 * legible at a glance rather than requiring the reader to parse labels.
 */
export const STANCE_ORDER: Stance[] = ["APPROVED", "SUPPORTED", "REQUESTED", "OPPOSED"];

// --- Read models -----------------------------------------------------------

/** Mirrors the `DecisionStance` dataclass. */
export type DecisionStance = {
  id: string;
  decision_id: string;
  workspace_id: string;
  /**
   * The name as recorded when the stance was taken. Free text, `NOT NULL`, and
   * **permanent** — it is audit data, not a denormalised copy of the directory.
   *
   * It stays even when `board_member_id` resolves, because the two answer different
   * questions: this is what was minuted, that is who the minute refers to. Collapsing
   * them would lose the record of what was actually written down.
   */
  person_name: string;
  /**
   * Optional resolution to the board directory. Shipped in CP5a (`0012_board_member`)
   * as a composite `(board_member_id, workspace_id)` foreign key, so a stance cannot
   * reference a director in another workspace.
   *
   * **Nullable forever.** A stance recorded before the directory existed, or against
   * someone who is not in it, is still a valid stance. Treat `null` as "not resolved",
   * never as an error, and never invent a name to fill it.
   */
  board_member_id: string | null;
  stance: Stance;
  comment: string | null;
  created_at: string; // ISO
  updated_at: string; // ISO
};

/** Mirrors the `Decision` dataclass. */
export type Decision = {
  id: string;
  meeting_id: string;
  agenda_item_id: string | null;
  workspace_id: string;
  title: string;
  rationale: string | null;
  status: DecisionStatus;
  /** Set when this decision was replaced; points at its replacement. */
  superseded_by_id: string | null;
  /** Optimistic-concurrency counter, not a published-version number. */
  version: number;
  created_at: string; // ISO
  updated_at: string; // ISO
  stances: DecisionStance[];
};

// --- Derived helpers -------------------------------------------------------

/** Counts by stance, in `STANCE_ORDER`, omitting stances nobody took. */
export function stanceBreakdown(d: Decision): { stance: Stance; count: number }[] {
  return STANCE_ORDER.map((stance) => ({
    stance,
    count: d.stances.filter((s) => s.stance === stance).length,
  })).filter((row) => row.count > 0);
}

/**
 * Follows `superseded_by_id` to the decision that replaced this one.
 *
 * Returns `null` rather than throwing when the target is absent: a reader may
 * hold a decision whose replacement they are not cleared to see, and a missing
 * link is a legitimate state, not an error.
 */
export function supersededBy(d: Decision, all: Decision[]): Decision | null {
  if (!d.superseded_by_id) return null;
  return all.find((x) => x.id === d.superseded_by_id) ?? null;
}

// --- Mock store ------------------------------------------------------------

const WS = "00000000-0000-0000-0000-000000000001";

/**
 * Names that resolve to the board directory in `board-members.ts`.
 *
 * Not every recorded name does, and that is the realistic case rather than an
 * oversight: `board_member_id` is nullable forever, and a stance minuted before the
 * directory existed still has to render.
 */
const DIRECTORY: Record<string, string> = {
  "Raj Malhotra": "bm-raj",
  "Priya Nair": "bm-priya",
  "Marcus Webb": "bm-marcus",
  "Elena Fischer": "bm-elena",
};

function stance(
  decision_id: string,
  n: number,
  person_name: string,
  s: Stance,
  comment: string | null,
  at: string,
): DecisionStance {
  return {
    id: `${decision_id}-s${n}`,
    decision_id,
    workspace_id: WS,
    person_name,
    // Resolved where the directory knows the name, null where it does not — the
    // shape the real column has, rather than a uniformly populated one that would
    // let an unresolved-stance bug go unnoticed.
    board_member_id: DIRECTORY[person_name] ?? null,
    stance: s,
    comment,
    created_at: at,
    updated_at: at,
  };
}

/**
 * Demo scenario data for the fictional Meridian board, shaped to exercise every
 * state the domain can reach: a live proposal, an approval with a full stance
 * spread, a rejection, a supersession pair, and a deferral.
 *
 * These are invented board decisions, in the same category as the meetings mock
 * — a fictional company's activity, not a claim about Callosum's measured
 * behaviour. The distinction that matters is in `insights.ts`: numbers that
 * describe the memory engine must be real or absent, while the demo company's
 * board minutes are scenario.
 */

// --- API client ------------------------------------------------------------

/**
 * Meridian decisions API. **Live; the in-memory mock is gone.**
 *
 * ---------------------------------------------------------------------------
 * THE SEVENTH CONTRACT DEFECT: THERE IS NO WORKSPACE-WIDE DECISIONS LIST
 * ---------------------------------------------------------------------------
 * The mock offered `list()` with no arguments, returning every decision in the
 * workspace. **The domain has never had that query.** `list_decisions(meeting_id, ...)`
 * requires a meeting, because a decision exists only in the context of one — so
 * `GET /api/decisions` requires `meeting_id` and refuses without it.
 *
 * Three surfaces were written against the mock's shape. Rather than invent a
 * workspace-wide endpoint during a feature freeze, `listForMeetings` fans out and
 * concatenates. That is N requests for N meetings, and it is exactly the round-trip
 * cost ADR-014 named when it chose 1:1 endpoints: *"a screen needing four aggregates
 * makes four round trips… neither bites at P3's scale… revisit at P6."* This is the
 * bill for that decision arriving, on schedule.
 */
export const decisionsApi = {
  /** Decisions for one meeting, newest first — the shape the API actually offers. */
  async listForMeeting(
    meetingId: string,
    opts?: { status?: DecisionStatus },
  ): Promise<Decision[]> {
    return apiGet<Decision[]>("/decisions", {
      meeting_id: meetingId,
      status: opts?.status,
    });
  },

  /**
   * Decisions across several meetings, newest first.
   *
   * Ordering is re-applied here because each request is sorted only within its own
   * meeting; concatenating them would interleave nothing and produce a list that is
   * sorted by meeting rather than by date.
   */
  async listForMeetings(
    meetingIds: string[],
    opts?: { status?: DecisionStatus },
  ): Promise<Decision[]> {
    if (meetingIds.length === 0) return [];
    const perMeeting = await Promise.all(
      meetingIds.map((id) => this.listForMeeting(id, opts)),
    );
    return perMeeting.flat().sort((a, b) => b.created_at.localeCompare(a.created_at));
  },

  async get(id: string): Promise<Decision | null> {
    return apiGetOrNull<Decision>(`/decisions/${encodeURIComponent(id)}`);
  },
};
