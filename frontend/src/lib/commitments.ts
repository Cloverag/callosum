import type { BadgeTone } from "@/components/ui/badge";

/**
 * Commitments — the accountable work a decision produced.
 *
 * Mirrors `meridian/commitments.py` and migration `0015_commitment` (PR #57, CP7),
 * with 42 integration tests behind it. Field names are snake_case and match the
 * Python dataclasses one for one, so the P3 swap is the `commitmentsApi` object and
 * nothing else.
 *
 * Where this file and `meridian/commitments.py` disagree, the Python is right.
 *
 * ---------------------------------------------------------------------------
 * TWO THINGS THIS SURFACE MUST NOT IMPLY
 * ---------------------------------------------------------------------------
 *
 * 1. **Nothing is dispatched anywhere.** `external_system`, `external_task_id`,
 *    `delivery_status` and `delivery_attempts` model retry *state*; no adapter
 *    exists and none will before P8. Every commitment is therefore
 *    `not_dispatched`, which is the only value the backend can currently produce.
 *    The mock does not invent `delivered` or `failed` rows and the UI renders no
 *    delivery section — a field on screen implies a feature behind it, and this is
 *    the same discipline that keeps `signing_state` off the resolutions card.
 *
 * 2. **`blocked` is not a dead end.** The proposal's original arrow left blocked
 *    work with no way back; the shipped domain allows `blocked → in_progress`. A
 *    surface that renders blocked as terminal would misreport recoverable work as
 *    abandoned.
 */

// --- Status ----------------------------------------------------------------

/** `meridian/commitments.py:38-42`. */
export type CommitmentStatus =
  | "open"
  | "in_progress"
  | "blocked"
  | "completed"
  | "cancelled";

export const COMMITMENT_STATUS_LABEL: Record<CommitmentStatus, string> = {
  open: "Open",
  in_progress: "In progress",
  blocked: "Blocked",
  completed: "Completed",
  cancelled: "Cancelled",
};

export const COMMITMENT_STATUS_TONE: Record<CommitmentStatus, BadgeTone> = {
  open: "info",
  in_progress: "accent",
  blocked: "warning",
  completed: "success",
  cancelled: "neutral",
};

export const COMMITMENT_STATUS_DOT: Record<CommitmentStatus, string> = {
  open: "bg-info",
  in_progress: "bg-accent",
  blocked: "bg-warning",
  completed: "bg-success",
  cancelled: "bg-subtle-foreground",
};

export const COMMITMENT_STATUSES = Object.keys(
  COMMITMENT_STATUS_LABEL,
) as CommitmentStatus[];

/**
 * The state machine, copied from `_ALLOWED_TRANSITIONS`.
 *
 * `blocked` is deliberately **not** terminal — blocked work is expected to resume.
 * Only `completed` and `cancelled` close. `open → completed` is absent on purpose:
 * it would skip the work.
 */
export const COMMITMENT_TRANSITIONS: Record<CommitmentStatus, CommitmentStatus[]> = {
  open: ["in_progress", "blocked", "cancelled"],
  in_progress: ["completed", "blocked", "cancelled"],
  blocked: ["in_progress", "cancelled"],
  completed: [],
  cancelled: [],
};

/** Statuses that still represent outstanding work — mirrors `Commitment.is_open`. */
export const OPEN_STATUSES: readonly CommitmentStatus[] = ["open", "in_progress", "blocked"];

export function isTerminal(status: CommitmentStatus): boolean {
  return COMMITMENT_TRANSITIONS[status].length === 0;
}

// --- Delivery (inert in P2 — see the note at the top) ----------------------

export type DeliveryStatus = "not_dispatched" | "pending" | "delivered" | "failed";

export const DELIVERY_STATUS_LABEL: Record<DeliveryStatus, string> = {
  not_dispatched: "Not dispatched",
  pending: "Dispatching",
  delivered: "Delivered",
  failed: "Delivery failed",
};

// --- Read models -----------------------------------------------------------

/** Mirrors the `CommitmentUpdate` dataclass. Append-only in the backend. */
export type CommitmentUpdate = {
  id: string;
  commitment_id: string;
  /** Required by the domain — a status change can never be recorded without a reason. */
  note: string;
  /** The status this update moved the commitment to, or `null` if it only reported progress. */
  new_status: CommitmentStatus | null;
  author_board_member_id: string | null;
  created_at: string; // ISO
  workspace_id: string;
};

/** Mirrors the `Commitment` dataclass. */
export type Commitment = {
  id: string;
  /** NOT NULL in the schema. A commitment cannot exist without a source decision. */
  decision_id: string;
  /** The formal instrument, when the decision produced one. */
  resolution_id: string | null;
  owner_board_member_id: string;
  accountable_team: string | null;
  title: string;
  detail: string | null;
  /** `DATE`, not a timestamp — a deadline is a calendar day. */
  due_date: string | null; // YYYY-MM-DD
  status: CommitmentStatus;
  completed_at: string | null; // ISO
  external_system: string | null;
  external_task_id: string | null;
  delivery_status: DeliveryStatus;
  delivery_attempts: number;
  version: number;
  created_at: string; // ISO
  updated_at: string; // ISO
  workspace_id: string;
  updates: CommitmentUpdate[];
};

// --- Derived helpers -------------------------------------------------------

/** Mirrors `Commitment.is_open`. */
export function isOpen(c: Commitment): boolean {
  return OPEN_STATUSES.includes(c.status);
}

/**
 * Mirrors `Commitment.is_overdue(today=...)`, including the awkward part.
 *
 * `today` is a parameter rather than `new Date()` for the same reason the Python
 * takes it: a value that changes under the caller makes a report irreproducible, and
 * this is exactly the kind of number that ends up on a dashboard. The page decides
 * what "today" is, once.
 *
 * Closed work is never overdue. It may have been *delivered* late, but an overdue
 * list that includes finished work is not an overdue list.
 */
export function isOverdue(c: Commitment, today: string): boolean {
  if (!c.due_date || !isOpen(c)) return false;
  // Both are YYYY-MM-DD, so a string compare is a date compare — and avoids the
  // timezone shift that parsing a bare date into a Date would introduce.
  return c.due_date < today;
}

/** Local calendar day as `YYYY-MM-DD`, for passing to `isOverdue`. */
export function todayLocal(now: Date = new Date()): string {
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/** The most recent update, or `null`. The trail is ordered oldest-first. */
export function latestUpdate(c: Commitment): CommitmentUpdate | null {
  return c.updates.length > 0 ? c.updates[c.updates.length - 1] : null;
}

// --- Mock store ------------------------------------------------------------

const WS = "00000000-0000-0000-0000-000000000001";

function update(
  commitment_id: string,
  n: number,
  note: string,
  new_status: CommitmentStatus | null,
  author: string | null,
  at: string,
): CommitmentUpdate {
  return {
    id: `${commitment_id}-u${n}`,
    commitment_id,
    note,
    new_status,
    author_board_member_id: author,
    created_at: at,
    workspace_id: WS,
  };
}

/**
 * Demo commitments for the fictional Meridian board.
 *
 * Scenario data, like the decisions, packs, minutes and resolutions mocks. Shaped to
 * exercise every state the domain reaches **and** the two a naive surface gets wrong:
 * work that is blocked and then resumes, and work completed after its due date.
 *
 * `decision_id` and `resolution_id` match the decisions and resolutions mocks, so all
 * three surfaces describe one company. Every row is `not_dispatched`, because that is
 * the only delivery state the backend can produce before P8.
 */
const mockCommitments: Commitment[] = [
  {
    id: "cmt-migration-plan",
    decision_id: "d-price-adopt",
    resolution_id: "res-pricing-v1",
    owner_board_member_id: "bm-priya",
    accountable_team: "Revenue Operations",
    title: "Produce the usage-based pricing migration plan",
    detail:
      "Board asked for the plan before any customer is moved. Must cover existing " +
      "annual contracts and the communications sequence.",
    due_date: "2026-08-14",
    status: "in_progress",
    completed_at: null,
    external_system: null,
    external_task_id: null,
    delivery_status: "not_dispatched",
    delivery_attempts: 0,
    version: 3,
    created_at: "2026-07-20T16:50:00Z",
    updated_at: "2026-07-26T09:15:00Z",
    workspace_id: WS,
    updates: [
      update("cmt-migration-plan", 1, "Drafting against the FY27 contract list.", "in_progress", "bm-priya", "2026-07-22T10:00:00Z"),
      update("cmt-migration-plan", 2, "Legal review of the annual-contract clause under way.", null, "bm-priya", "2026-07-26T09:15:00Z"),
    ],
  },
  {
    id: "cmt-preference-model",
    decision_id: "d-terms",
    resolution_id: null,
    owner_board_member_id: "bm-marcus",
    accountable_team: null,
    title: "Model the Series B liquidation preference stack",
    detail: "Requested before the board votes on final terms.",
    // Deliberately in the past and still open — the overdue path has to render.
    due_date: "2026-07-25",
    status: "blocked",
    completed_at: null,
    external_system: null,
    external_task_id: null,
    delivery_status: "not_dispatched",
    delivery_attempts: 0,
    version: 4,
    created_at: "2026-07-21T09:30:00Z",
    updated_at: "2026-07-27T14:00:00Z",
    workspace_id: WS,
    updates: [
      update("cmt-preference-model", 1, "Started against the draft term sheet.", "in_progress", "bm-marcus", "2026-07-22T11:00:00Z"),
      update("cmt-preference-model", 2, "Blocked — waiting on the final term sheet from Sequoia.", "blocked", "bm-marcus", "2026-07-27T14:00:00Z"),
    ],
  },
  {
    id: "cmt-hiring-reqs",
    decision_id: "d-hire",
    resolution_id: "res-hiring",
    owner_board_member_id: "bm-raj",
    accountable_team: "People",
    title: "Open six engineering requisitions for FY27",
    detail: null,
    due_date: "2026-07-31",
    status: "open",
    completed_at: null,
    external_system: null,
    external_task_id: null,
    delivery_status: "not_dispatched",
    delivery_attempts: 0,
    version: 1,
    created_at: "2026-07-09T11:40:00Z",
    updated_at: "2026-07-09T11:40:00Z",
    workspace_id: WS,
    updates: [],
  },
  {
    id: "cmt-forecast-revision",
    decision_id: "d-fcst",
    resolution_id: null,
    owner_board_member_id: "bm-priya",
    accountable_team: "Finance",
    title: "Bring the revised FY27 forecast to the next cycle",
    detail: "Deferred pending the Q4 audit numbers.",
    // Completed AFTER its due date. Late, but not outstanding — so it must not
    // appear on an overdue list.
    due_date: "2026-07-24",
    status: "completed",
    completed_at: "2026-07-28T16:00:00Z",
    external_system: null,
    external_task_id: null,
    delivery_status: "not_dispatched",
    delivery_attempts: 0,
    version: 4,
    created_at: "2026-07-21T09:45:00Z",
    updated_at: "2026-07-28T16:00:00Z",
    workspace_id: WS,
    updates: [
      update("cmt-forecast-revision", 1, "Audit numbers received.", "in_progress", "bm-priya", "2026-07-27T10:00:00Z"),
      update("cmt-forecast-revision", 2, "Revised forecast circulated to the board.", "completed", "bm-priya", "2026-07-28T16:00:00Z"),
    ],
  },
  {
    id: "cmt-berlin-scout",
    decision_id: "d-office",
    resolution_id: "res-berlin",
    owner_board_member_id: "bm-elena",
    accountable_team: null,
    title: "Scout Berlin office locations",
    detail: "Cancelled when the board rejected the second office for FY27.",
    due_date: null,
    status: "cancelled",
    completed_at: null,
    external_system: null,
    external_task_id: null,
    delivery_status: "not_dispatched",
    delivery_attempts: 0,
    version: 2,
    created_at: "2026-07-09T11:30:00Z",
    updated_at: "2026-07-09T11:35:00Z",
    workspace_id: WS,
    updates: [
      update("cmt-berlin-scout", 1, "Cancelled — resolution 2026-02 was not approved.", "cancelled", "bm-raj", "2026-07-09T11:35:00Z"),
    ],
  },
];

const clone = (c: Commitment): Commitment => structuredClone(c);
const delay = (ms = 400) => new Promise((r) => setTimeout(r, ms));

/**
 * Mocked Meridian commitments API.
 *
 * Method names and arguments follow `meridian/commitments.py`. Ordering matches
 * `list_commitments`: soonest due first, **undated last** — a commitment with no
 * deadline is not the most urgent thing on the list.
 */
export const commitmentsApi = {
  async list(opts?: {
    decision_id?: string;
    owner_board_member_id?: string;
    status?: CommitmentStatus;
    open_only?: boolean;
  }): Promise<Commitment[]> {
    await delay();
    return mockCommitments
      .filter((c) => (opts?.decision_id ? c.decision_id === opts.decision_id : true))
      .filter((c) =>
        opts?.owner_board_member_id
          ? c.owner_board_member_id === opts.owner_board_member_id
          : true,
      )
      .filter((c) => (opts?.status ? c.status === opts.status : true))
      .filter((c) => (opts?.open_only ? OPEN_STATUSES.includes(c.status) : true))
      .slice()
      .sort((a, b) => {
        if (a.due_date && b.due_date) {
          return a.due_date.localeCompare(b.due_date) || b.created_at.localeCompare(a.created_at);
        }
        if (a.due_date) return -1; // NULLS LAST
        if (b.due_date) return 1;
        return b.created_at.localeCompare(a.created_at);
      })
      .map(clone);
  },

  async get(id: string): Promise<Commitment | null> {
    await delay(200);
    const c = mockCommitments.find((x) => x.id === id);
    return c ? clone(c) : null;
  },
};
