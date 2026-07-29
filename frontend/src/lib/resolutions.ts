import type { BadgeTone } from "@/components/ui/badge";
import { apiGet, apiGetOrNull } from "@/lib/http";

/**
 * Resolutions — the formal instrument a decision produced, and the votes cast on it.
 *
 * **Live against the API as of CP-B/B3.** `resolutionsApi` calls
 * `GET /api/resolutions`, which is `meridian/resolutions.py` behind
 * `meridian/api/resolutions.py`. The in-memory mock this file used to carry is gone;
 * the swap was the `resolutionsApi` object and nothing else, because the types below
 * were written against the Python dataclasses field-for-field from the start.
 *
 * That correspondence is now enforced rather than trusted:
 * `tests/test_resolutions_api.py` reads the `Resolution` type out of this file and
 * compares it to what the endpoint actually serialises, so drift fails a build
 * instead of surfacing in a browser.
 *
 * Where this file and `meridian/resolutions.py` disagree, the Python is right.
 *
 * ---------------------------------------------------------------------------
 * TWO THINGS THIS SURFACE MUST NOT CLAIM
 * ---------------------------------------------------------------------------
 *
 * 1. **The tally does not decide the outcome.** `carried` is a simple majority of
 *    votes actually cast, and it is advisory. Quorum and supermajority rules vary
 *    per board and this system has nowhere to record them, so presenting the tally
 *    as the result would assert a governance rule nobody configured. `status` is
 *    authoritative and a human sets it — the backend has a test that adopts a
 *    motion the tally says did not carry, and the UI must be able to render that
 *    without looking broken.
 *
 * 2. **Nothing here is legally executed.** `signing_state` is a single-value enum
 *    pinned to `not_applicable`. E-signature, legal validity and jurisdiction are
 *    P8. No label on this surface may imply a resolution has been signed, executed,
 *    or is binding.
 */

// --- Status ----------------------------------------------------------------

/** `meridian/resolutions.py:29-32`. There is deliberately no `archived`. */
export type ResolutionStatus = "draft" | "adopted" | "rejected" | "superseded";

export const RESOLUTION_STATUS_LABEL: Record<ResolutionStatus, string> = {
  draft: "Draft",
  adopted: "Adopted",
  rejected: "Rejected",
  superseded: "Superseded",
};

export const RESOLUTION_STATUS_TONE: Record<ResolutionStatus, BadgeTone> = {
  draft: "neutral",
  adopted: "success",
  rejected: "danger",
  superseded: "neutral",
};

export const RESOLUTION_STATUS_DOT: Record<ResolutionStatus, string> = {
  draft: "bg-muted-foreground",
  adopted: "bg-success",
  rejected: "bg-danger",
  superseded: "bg-subtle-foreground",
};

export const RESOLUTION_STATUSES = Object.keys(RESOLUTION_STATUS_LABEL) as ResolutionStatus[];

/**
 * The domain state machine, copied from `_ALLOWED_TRANSITIONS`.
 *
 * `adopted` is terminal here because its only exit is `supersede_resolution()`,
 * which creates a *new* record rather than mutating this one — that is what keeps
 * an adopted resolution immutable.
 */
export const RESOLUTION_TRANSITIONS: Record<ResolutionStatus, ResolutionStatus[]> = {
  draft: ["adopted", "rejected"],
  adopted: [],
  rejected: [],
  superseded: [],
};

/** True when the only way forward is a new version. */
export function isTerminal(status: ResolutionStatus): boolean {
  return RESOLUTION_TRANSITIONS[status].length === 0;
}

// --- Votes -----------------------------------------------------------------

/** `meridian/resolutions.py:44-47`. */
export type Vote = "for" | "against" | "abstain" | "recused";

export const VOTE_LABEL: Record<Vote, string> = {
  for: "For",
  against: "Against",
  abstain: "Abstained",
  recused: "Recused",
};

export const VOTE_TONE: Record<Vote, BadgeTone> = {
  for: "success",
  against: "danger",
  abstain: "neutral",
  recused: "warning",
};

/**
 * Display order: a spectrum from assent to dissent, then the two non-votes.
 * Deliberately not alphabetical — the shape of the board's position should be
 * legible without parsing labels. Same reasoning as `STANCE_ORDER` in `decisions.ts`.
 */
export const VOTE_ORDER: Vote[] = ["for", "against", "abstain", "recused"];

/**
 * The votes that weigh on the outcome, from `_COUNTED_VOTES`.
 *
 * An abstention is a deliberate non-vote and a recusal is a declared conflict.
 * Counting either as opposition would misreport the board.
 */
export const COUNTED_VOTES: readonly Vote[] = ["for", "against"];

// --- Read models -----------------------------------------------------------

/** Mirrors the `ResolutionVote` dataclass. */
export type ResolutionVote = {
  id: string;
  resolution_id: string;
  /**
   * A real foreign key to the board directory, unlike `decision_stance.person_name`
   * which is free text. CP5a made the directory the source of truth for who voted,
   * so this surface resolves ids to people rather than rendering a recorded string.
   */
  board_member_id: string;
  vote: Vote;
  created_at: string; // ISO — when they first voted, never rewritten
  updated_at: string; // ISO — when they last changed it
  workspace_id: string;
};

/** Mirrors the `Resolution` dataclass. */
export type Resolution = {
  id: string;
  decision_id: string;
  title: string;
  body: string;
  status: ResolutionStatus;
  /** One value only. See the note at the top of this file. */
  signing_state: "not_applicable";
  /** Published-artifact lineage. Distinct from `version` — see CONTRIBUTING.md. */
  version_no: number;
  superseded_by_id: string | null;
  adopted_at: string | null; // ISO
  /** Optimistic-concurrency counter, not a published-version number. */
  version: number;
  created_at: string; // ISO
  updated_at: string; // ISO
  workspace_id: string;
  votes: ResolutionVote[];
};

// --- Derived helpers -------------------------------------------------------

export type Tally = {
  for: number;
  against: number;
  abstain: number;
  recused: number;
  /** Votes that weigh: `for + against`. */
  counted: number;
  /**
   * A simple majority of votes cast. **Advisory only** — see the note at the top.
   * Never render this as the outcome; `status` is the outcome.
   */
  carried: boolean;
};

/** Ports `meridian.resolutions.tally`. Pure. */
export function tally(resolution: Resolution): Tally {
  const counts: Record<Vote, number> = { for: 0, against: 0, abstain: 0, recused: 0 };
  for (const v of resolution.votes) counts[v.vote] += 1;
  return {
    ...counts,
    counted: counts.for + counts.against,
    carried: counts.for > counts.against,
  };
}

/**
 * True when the recorded outcome differs from what a simple majority would suggest.
 *
 * Not an error state. A board can adopt against the arithmetic — a chair's casting
 * vote, a weighted share class, a rule this system was never told. The surface
 * shows it as context so the reader is not left thinking the page is wrong, which
 * is the honest alternative to silently hiding the discrepancy.
 */
export function outcomeDivergesFromTally(resolution: Resolution): boolean {
  if (resolution.status !== "adopted" && resolution.status !== "rejected") return false;
  const t = tally(resolution);
  if (t.counted === 0) return false;
  return resolution.status === "adopted" ? !t.carried : t.carried;
}

/**
 * Follows `superseded_by_id` to the version that replaced this one.
 *
 * Returns `null` rather than throwing when the target is absent, matching
 * `supersededBy` in `decisions.ts`, `packs.ts` and `minutes.ts`.
 */
export function supersededBy(r: Resolution, all: Resolution[]): Resolution | null {
  if (!r.superseded_by_id) return null;
  return all.find((x) => x.id === r.superseded_by_id) ?? null;
}

// --- API client ------------------------------------------------------------

/**
 * Meridian resolutions API.
 *
 * Real HTTP as of CP-B/B3; the in-memory mock this replaced lived here until the
 * endpoints existed. **The exported shape is unchanged** — same method names, same
 * arguments, same return types — which is what lets every calling surface and every
 * component stay exactly as it was.
 *
 * `workspace_id` is absent from these calls and has nowhere to be passed. The API
 * derives it from the session cookie on every request (ADR-013).
 *
 * Ordering is the server's: `version_no DESC, created_at DESC`, from
 * `list_resolutions`. The client does not re-sort, because a second ordering is a
 * second thing that can disagree with the first.
 */
export const resolutionsApi = {
  async list(opts?: {
    decision_id?: string;
    status?: ResolutionStatus;
  }): Promise<Resolution[]> {
    return apiGet<Resolution[]>("/resolutions", {
      decision_id: opts?.decision_id,
      status: opts?.status,
    });
  },

  async get(id: string): Promise<Resolution | null> {
    // `null` for a missing resolution, preserving the mock's contract so the pages
    // that already render "not found" keep working. A 403 still throws — being
    // refused is not the same as it not existing, and collapsing them would hide a
    // permissions problem behind an empty state.
    return apiGetOrNull<Resolution>(`/resolutions/${encodeURIComponent(id)}`);
  },
};
