import type { Resolution, ResolutionVote } from "@/lib/resolutions";

/**
 * Resolution fixtures for the frontend unit tests.
 *
 * These were the `mockResolutions` store inside `lib/resolutions.ts` until CP-B/B3
 * replaced it with a real API client. The data moved here rather than being deleted:
 * the assertions it supports are contract assertions — the advisory tally, the
 * unvoted supersession, the inert `signing_state` — and they are worth keeping
 * whether the bytes arrive from a mock or from Postgres.
 *
 * **Not shipped.** Nothing under `src/` imports this; it exists so the tests can stub
 * `fetch` with a known payload and stay unit tests, per the CP-B acceptance criteria.
 *
 * `board_member_id` values match `lib/board-members.ts`, so the "every vote resolves
 * to a real director" assertion still crosses the two modules the way it did before.
 */

const WS = "00000000-0000-0000-0000-000000000001";

function vote(
  resolution_id: string,
  n: number,
  board_member_id: string,
  v: ResolutionVote["vote"],
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

export const RESOLUTION_FIXTURES: Resolution[] = [
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
