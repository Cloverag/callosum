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
   * Free text in the backend today — `decision_stance.person_name` is a TEXT
   * column with no foreign key, so two spellings of one director are two people.
   * CP5 (issue #36) adds a nullable `board_member_id`; until then this is the
   * only identifier available and the UI must not imply it is resolvable.
   */
  person_name: string;
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
const mockDecisions: Decision[] = [
  {
    id: "d-price-reject",
    meeting_id: "m-14",
    agenda_item_id: "a2",
    workspace_id: WS,
    title: "Reject Pricing Model B for FY27",
    rationale: "Metered billing was judged too risky ahead of the Series B close.",
    status: "superseded",
    superseded_by_id: "d-price-adopt",
    version: 3,
    created_at: "2026-07-09T10:35:00Z",
    updated_at: "2026-07-20T16:40:00Z",
    stances: [
      stance("d-price-reject", 1, "Raj Malhotra", "APPROVED", "We're not doing Model B.", "2026-07-09T10:36:00Z"),
      stance("d-price-reject", 2, "Priya Nair", "SUPPORTED", "Agreed — the forecast doesn't support it yet.", "2026-07-09T10:37:00Z"),
      stance("d-price-reject", 3, "Marcus Webb", "OPPOSED", "I think we're leaving revenue on the table.", "2026-07-09T10:38:00Z"),
      stance("d-price-reject", 4, "Elena Fischer", "SUPPORTED", null, "2026-07-09T10:39:00Z"),
    ],
  },
  {
    id: "d-price-adopt",
    meeting_id: "m-q3",
    agenda_item_id: "b3",
    workspace_id: WS,
    title: "Adopt usage-based pricing (Model B)",
    rationale: "Reversed after the Q2 cohort data showed metered accounts retaining better.",
    status: "approved",
    superseded_by_id: null,
    version: 2,
    created_at: "2026-07-20T16:38:00Z",
    updated_at: "2026-07-20T16:40:00Z",
    stances: [
      stance("d-price-adopt", 1, "Raj Malhotra", "APPROVED", "On reflection we're moving ahead with usage-based pricing after all.", "2026-07-20T16:39:00Z"),
      stance("d-price-adopt", 2, "Marcus Webb", "SUPPORTED", null, "2026-07-20T16:39:30Z"),
      stance("d-price-adopt", 3, "Priya Nair", "REQUESTED", "Fine, but I want the migration plan minuted.", "2026-07-20T16:40:00Z"),
    ],
  },
  {
    id: "d-seq",
    meeting_id: "m-seq",
    agenda_item_id: null,
    workspace_id: WS,
    title: "Sequoia to lead the Series B round",
    rationale: null,
    status: "approved",
    superseded_by_id: null,
    version: 2,
    created_at: "2026-07-19T11:00:00Z",
    updated_at: "2026-07-19T11:05:00Z",
    stances: [
      stance("d-seq", 1, "Raj Malhotra", "APPROVED", "Sequoia has confirmed they'll lead the Series B at the proposed valuation.", "2026-07-19T11:05:00Z"),
      stance("d-seq", 2, "Elena Fischer", "SUPPORTED", null, "2026-07-19T11:05:30Z"),
    ],
  },
  {
    id: "d-terms",
    meeting_id: "m-q3",
    agenda_item_id: "b3",
    workspace_id: WS,
    title: "Series B final terms",
    rationale: "Liquidation preference and board composition still open.",
    status: "proposed",
    superseded_by_id: null,
    version: 1,
    created_at: "2026-07-21T09:20:00Z",
    updated_at: "2026-07-21T09:20:00Z",
    stances: [
      stance("d-terms", 1, "Marcus Webb", "REQUESTED", "I want the preference stack modelled before we vote.", "2026-07-21T09:25:00Z"),
    ],
  },
  {
    id: "d-hire",
    meeting_id: "m-14",
    agenda_item_id: "a3",
    workspace_id: WS,
    title: "Six-person engineering hire",
    rationale: "Signed off against the FY27 plan.",
    status: "approved",
    superseded_by_id: null,
    version: 2,
    created_at: "2026-07-09T11:15:00Z",
    updated_at: "2026-07-09T11:20:00Z",
    stances: [
      stance("d-hire", 1, "Raj Malhotra", "APPROVED", "We signed off on the six-engineer hiring plan for the half.", "2026-07-09T11:20:00Z"),
      stance("d-hire", 2, "Priya Nair", "SUPPORTED", null, "2026-07-09T11:20:30Z"),
    ],
  },
  {
    id: "d-fcst",
    meeting_id: "m-q3",
    agenda_item_id: "b2",
    workspace_id: WS,
    title: "Revise the FY27 forecast",
    rationale: "Deferred pending the Q4 audit numbers.",
    status: "deferred",
    superseded_by_id: null,
    version: 2,
    created_at: "2026-07-21T09:15:00Z",
    updated_at: "2026-07-21T09:40:00Z",
    stances: [
      stance("d-fcst", 1, "Priya Nair", "REQUESTED", "Priya will bring the revised FY27 forecast to the next cycle.", "2026-07-21T09:30:00Z"),
    ],
  },
  {
    id: "d-office",
    meeting_id: "m-14",
    agenda_item_id: null,
    workspace_id: WS,
    title: "Open a second office in Berlin",
    rationale: "Rejected on runway grounds.",
    status: "rejected",
    superseded_by_id: null,
    version: 2,
    created_at: "2026-07-09T11:25:00Z",
    updated_at: "2026-07-09T11:28:00Z",
    stances: [
      stance("d-office", 1, "Priya Nair", "OPPOSED", "Not before the B closes.", "2026-07-09T11:26:00Z"),
      stance("d-office", 2, "Raj Malhotra", "OPPOSED", null, "2026-07-09T11:27:00Z"),
    ],
  },
];

const clone = (d: Decision): Decision => structuredClone(d);
const delay = (ms = 400) => new Promise((r) => setTimeout(r, ms));

/**
 * Mocked Meridian decisions API.
 *
 * Method names and arguments follow `meridian/decisions.py` so the P3 swap is
 * mechanical. Ordering matches `list_decisions`: newest first.
 */
export const decisionsApi = {
  async list(opts?: { status?: DecisionStatus; meeting_id?: string }): Promise<Decision[]> {
    await delay();
    return mockDecisions
      .filter((d) => (opts?.status ? d.status === opts.status : true))
      .filter((d) => (opts?.meeting_id ? d.meeting_id === opts.meeting_id : true))
      .slice()
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .map(clone);
  },

  async get(id: string): Promise<Decision | null> {
    await delay(200);
    const d = mockDecisions.find((x) => x.id === id);
    return d ? clone(d) : null;
  },
};
