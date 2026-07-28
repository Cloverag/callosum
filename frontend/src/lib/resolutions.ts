import type { BadgeTone } from "@/components/ui/badge";

/**
 * Resolutions — the formal instrument a decision produced, and the votes cast on it.
 *
 * Mirrors `meridian/resolutions.py` and migration `0014_resolution` (PR #54, CP6),
 * with 32 integration tests behind it. Field names are snake_case and match the
 * Python dataclasses one for one, so the P3 swap is the `resolutionsApi` object and
 * nothing else.
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

// --- Mock store ------------------------------------------------------------

const WS = "00000000-0000-0000-0000-000000000001";

function vote(
  resolution_id: string,
  n: number,
  board_member_id: string,
  v: Vote,
  at: string,
): ResolutionVote {
  return {
    id: `${resolution_id}-v${n}`,
    resolution_id,
    board_member_id,
    vote: v,
    created_at: at,
    updated_at: at,
    workspace_id: WS,
  };
}

/**
 * Demo resolutions for the fictional Meridian board.
 *
 * Scenario data, in the same category as the decisions, packs and minutes mocks.
 * Shaped to exercise every state the domain reaches AND the two cases a naive
 * surface gets wrong: a motion adopted against the arithmetic, and a supersession
 * pair where the new version starts unvoted.
 *
 * `decision_id` values match the decisions in `decisions.ts`, so the two surfaces
 * describe one company.
 */
const mockResolutions: Resolution[] = [
  {
    id: "res-pricing-v1",
    decision_id: "d-price-adopt",
    title: "Resolution 2026-04 — adoption of usage-based pricing",
    body:
      "RESOLVED THAT the Company shall adopt the usage-based pricing model (Model B) " +
      "for FY27, with effect from the start of the next billing cycle, and that the " +
      "migration plan shall be presented to the Board before any customer is moved.",
    status: "superseded",
    signing_state: "not_applicable",
    version_no: 1,
    superseded_by_id: "res-pricing-v2",
    adopted_at: "2026-07-20T16:45:00Z",
    version: 5,
    created_at: "2026-07-20T16:41:00Z",
    updated_at: "2026-07-22T11:00:00Z",
    workspace_id: WS,
    votes: [
      vote("res-pricing-v1", 1, "bm-raj", "for", "2026-07-20T16:42:00Z"),
      vote("res-pricing-v1", 2, "bm-marcus", "for", "2026-07-20T16:42:30Z"),
      vote("res-pricing-v1", 3, "bm-priya", "abstain", "2026-07-20T16:43:00Z"),
      vote("res-pricing-v1", 4, "bm-elena", "for", "2026-07-20T16:43:30Z"),
    ],
  },
  {
    id: "res-pricing-v2",
    decision_id: "d-price-adopt",
    title: "Resolution 2026-04A — adoption of usage-based pricing (as amended)",
    body:
      "RESOLVED THAT the Company shall adopt the usage-based pricing model (Model B) " +
      "for FY27, with effect from the start of the next billing cycle; that the " +
      "migration plan shall be presented to the Board before any customer is moved; " +
      "and that existing annual contracts shall be honoured to their renewal date.",
    status: "draft",
    signing_state: "not_applicable",
    version_no: 2,
    superseded_by_id: null,
    adopted_at: null,
    version: 1,
    created_at: "2026-07-22T11:00:00Z",
    updated_at: "2026-07-22T11:00:00Z",
    workspace_id: WS,
    // Deliberately unvoted: supersession does not carry votes forward, because they
    // were cast on the old wording.
    votes: [],
  },
  {
    id: "res-seriesb",
    decision_id: "d-seq",
    title: "Resolution 2026-05 — appointment of Sequoia as lead investor",
    body:
      "RESOLVED THAT the Board approves Sequoia Capital as lead investor for the " +
      "Series B round at the valuation set out in the term sheet dated 12 July 2026, " +
      "subject to completion of confirmatory diligence.",
    status: "adopted",
    signing_state: "not_applicable",
    version_no: 1,
    superseded_by_id: null,
    adopted_at: "2026-07-19T11:20:00Z",
    version: 4,
    created_at: "2026-07-19T11:10:00Z",
    updated_at: "2026-07-19T11:20:00Z",
    workspace_id: WS,
    votes: [
      vote("res-seriesb", 1, "bm-raj", "for", "2026-07-19T11:12:00Z"),
      vote("res-seriesb", 2, "bm-elena", "recused", "2026-07-19T11:13:00Z"),
      vote("res-seriesb", 3, "bm-marcus", "for", "2026-07-19T11:14:00Z"),
      vote("res-seriesb", 4, "bm-priya", "for", "2026-07-19T11:15:00Z"),
    ],
  },
  {
    id: "res-hiring",
    decision_id: "d-hire",
    title: "Resolution 2026-03 — FY27 engineering headcount",
    body:
      "RESOLVED THAT the Company is authorised to recruit up to six additional " +
      "engineering staff during FY27 within the approved budget envelope.",
    status: "adopted",
    signing_state: "not_applicable",
    version_no: 1,
    superseded_by_id: null,
    adopted_at: "2026-07-09T11:35:00Z",
    version: 4,
    created_at: "2026-07-09T11:22:00Z",
    updated_at: "2026-07-09T11:35:00Z",
    workspace_id: WS,
    // Adopted 1-for / 1-against: the tally does not carry, and the Board adopted it
    // anyway on the chair's casting vote. The surface must render this without
    // looking broken — see `outcomeDivergesFromTally`.
    votes: [
      vote("res-hiring", 1, "bm-raj", "for", "2026-07-09T11:30:00Z"),
      vote("res-hiring", 2, "bm-marcus", "against", "2026-07-09T11:31:00Z"),
      vote("res-hiring", 3, "bm-tobi", "recused", "2026-07-09T11:32:00Z"),
    ],
  },
  {
    id: "res-berlin",
    decision_id: "d-office",
    title: "Resolution 2026-02 — second office (Berlin)",
    body:
      "RESOLVED THAT the proposal to open a second office in Berlin during FY27 is " +
      "not approved, and shall not be reconsidered before the close of the Series B.",
    status: "rejected",
    signing_state: "not_applicable",
    version_no: 1,
    superseded_by_id: null,
    adopted_at: null,
    version: 3,
    created_at: "2026-07-09T11:26:00Z",
    updated_at: "2026-07-09T11:29:00Z",
    workspace_id: WS,
    votes: [
      vote("res-berlin", 1, "bm-priya", "against", "2026-07-09T11:27:00Z"),
      vote("res-berlin", 2, "bm-raj", "against", "2026-07-09T11:27:30Z"),
      vote("res-berlin", 3, "bm-elena", "abstain", "2026-07-09T11:28:00Z"),
    ],
  },
];

const clone = (r: Resolution): Resolution => structuredClone(r);
const delay = (ms = 400) => new Promise((r) => setTimeout(r, ms));

/**
 * Mocked Meridian resolutions API.
 *
 * Method names and arguments follow `meridian/resolutions.py`, and ordering matches
 * `list_resolutions`: `version_no DESC, created_at DESC`.
 */
export const resolutionsApi = {
  async list(opts?: {
    decision_id?: string;
    status?: ResolutionStatus;
  }): Promise<Resolution[]> {
    await delay();
    return mockResolutions
      .filter((r) => (opts?.decision_id ? r.decision_id === opts.decision_id : true))
      .filter((r) => (opts?.status ? r.status === opts.status : true))
      .slice()
      .sort(
        (a, b) =>
          b.version_no - a.version_no || b.created_at.localeCompare(a.created_at),
      )
      .map(clone);
  },

  async get(id: string): Promise<Resolution | null> {
    await delay(200);
    const r = mockResolutions.find((x) => x.id === id);
    return r ? clone(r) : null;
  },
};
