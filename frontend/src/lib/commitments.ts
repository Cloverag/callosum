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
import { apiGet, apiGetOrNull } from "@/lib/http";

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

// --- API client ------------------------------------------------------------

/**
 * Meridian commitments API. **Live; the in-memory mock is gone.**
 *
 * The mock survived CP-C because the backend endpoint landed in the same checkpoint
 * and the client swap was never done — found by running the application and seeing
 * seeded commitments missing from a page that was rendering fabricated ones.
 *
 * All four filters are the domain's own. `open_only` is the one that earns its place:
 * "what is still outstanding" is the question a board asks, and no single status
 * answers it.
 */
export const commitmentsApi = {
  async list(opts?: {
    decision_id?: string;
    owner_board_member_id?: string;
    status?: CommitmentStatus;
    open_only?: boolean;
  }): Promise<Commitment[]> {
    return apiGet<Commitment[]>("/commitments", {
      decision_id: opts?.decision_id,
      owner_board_member_id: opts?.owner_board_member_id,
      status: opts?.status,
      open_only: opts?.open_only ? "true" : undefined,
    });
  },

  async get(id: string): Promise<Commitment | null> {
    return apiGetOrNull<Commitment>(`/commitments/${encodeURIComponent(id)}`);
  },
};
