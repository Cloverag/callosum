import type { Decision, DecisionStance } from "@/lib/decisions";
import type { Resolution, ResolutionVote } from "@/lib/resolutions";
import type { Commitment, CommitmentUpdate } from "@/lib/commitments";
import type { BoardPack, BoardPackItem } from "@/lib/packs";
import type { Minutes } from "@/lib/minutes";
import type { EntityConflict } from "@/lib/api";
import {
  COMMITMENT, CONFLICT, DECISION, DEMO_WORKSPACE_ID, DOCUMENT, MEETING,
  MEMBER, MINUTES, PACK, PACK_ITEM, RESOLUTION, STANCE, UPDATE, VOTE,
} from "./ids";

const stance = (
  n: number, decision: string, person: string, member: string | null,
  s: DecisionStance["stance"], comment: string | null,
): DecisionStance => ({
  id: STANCE[n], decision_id: decision, workspace_id: DEMO_WORKSPACE_ID,
  person_name: person, board_member_id: member, stance: s, comment,
  created_at: "2026-07-15T14:10:00Z", updated_at: "2026-07-15T14:10:00Z",
});

/**
 * Six decisions covering all five `DecisionStatus` values.
 *
 * One is superseded and points at its successor, because
 * `DECISION_TRANSITIONS` treats that as terminal and the surface renders a link
 * to the replacement — a link that is dead in any fixture set where
 * `superseded_by_id` is always null.
 *
 * `stances` is populated unevenly on purpose: one decision has four, two have
 * one each, and the rest have none. A stance list is optional in the model and
 * the empty case is the common one in real data.
 */
export const DECISIONS: Decision[] = [
  {
    id: DECISION[0], meeting_id: MEETING[0], agenda_item_id: null,
    workspace_id: DEMO_WORKSPACE_ID, title: "Approve the FY27 operating budget",
    rationale: "Headcount plan holds runway past the Series B close.",
    status: "approved", superseded_by_id: null, version: 2,
    created_at: "2026-07-15T14:05:00Z", updated_at: "2026-07-15T14:40:00Z",
    stances: [
      stance(0, DECISION[0], "Amara Okonkwo", MEMBER[0], "SUPPORTED", null),
      stance(1, DECISION[0], "Daniel Reyes", MEMBER[1], "APPROVED", "Subject to the hiring freeze in Q1."),
      stance(2, DECISION[0], "Tomás Lindqvist", MEMBER[3], "REQUESTED", "Would like the sensitivity case circulated."),
      stance(3, DECISION[0], "Priya Raghunathan", MEMBER[2], "OPPOSED", "Sales headcount is ahead of pipeline."),
    ],
  },
  {
    id: DECISION[1], meeting_id: MEETING[1], agenda_item_id: null,
    workspace_id: DEMO_WORKSPACE_ID, title: "Accept the Series B term sheet",
    rationale: "Valuation and the liquidation preference are both within the mandate.",
    status: "approved", superseded_by_id: null, version: 3,
    created_at: "2026-08-05T16:20:00Z", updated_at: "2026-08-05T16:55:00Z",
    stances: [
      stance(4, DECISION[1], "Priya Raghunathan", MEMBER[2], "SUPPORTED", "Recused from the vote; supportive in discussion."),
    ],
  },
  {
    id: DECISION[2], meeting_id: MEETING[1], agenda_item_id: null,
    workspace_id: DEMO_WORKSPACE_ID, title: "Appoint an independent chair",
    rationale: null, status: "deferred", superseded_by_id: null, version: 1,
    created_at: "2026-08-05T16:40:00Z", updated_at: "2026-08-05T16:40:00Z",
    stances: [],
  },
  {
    // Superseded, and it names its replacement.
    id: DECISION[3], meeting_id: MEETING[0], agenda_item_id: null,
    workspace_id: DEMO_WORKSPACE_ID, title: "Open a São Paulo office in Q4",
    rationale: "Superseded by the phased plan agreed in August.",
    status: "superseded", superseded_by_id: DECISION[4], version: 4,
    created_at: "2026-07-15T14:50:00Z", updated_at: "2026-08-05T16:05:00Z",
    stances: [],
  },
  {
    id: DECISION[4], meeting_id: MEETING[1], agenda_item_id: null,
    workspace_id: DEMO_WORKSPACE_ID, title: "Open a São Paulo office in two phases",
    rationale: "Sales-only in Q4; engineering deferred to the FY28 plan.",
    status: "proposed", superseded_by_id: null, version: 1,
    created_at: "2026-08-05T16:05:00Z", updated_at: "2026-08-05T16:05:00Z",
    stances: [
      stance(5, DECISION[4], "Daniel Reyes", MEMBER[1], "SUPPORTED", null),
    ],
  },
  {
    id: DECISION[5], meeting_id: MEETING[3], agenda_item_id: null,
    workspace_id: DEMO_WORKSPACE_ID, title: "Adopt the revised risk appetite statement",
    rationale: null, status: "rejected", superseded_by_id: null, version: 2,
    created_at: "2026-09-02T09:20:00Z", updated_at: "2026-09-02T09:35:00Z",
    stances: [],
  },
];

const vote = (n: number, resolution: string, member: string, v: ResolutionVote["vote"]): ResolutionVote => ({
  id: VOTE[n], resolution_id: resolution, board_member_id: member, vote: v,
  created_at: "2026-07-15T14:30:00Z", updated_at: "2026-07-15T14:30:00Z",
  workspace_id: DEMO_WORKSPACE_ID,
});

/**
 * Four resolutions, one per `ResolutionStatus`.
 *
 * `RESOLUTION[0]`'s votes include an abstention and a recusal, so `tally`'s
 * distinction between cast votes and *counted* votes (`for + against`) is
 * visible rather than notional — with four votes on screen and a counted total
 * of two.
 *
 * `RESOLUTION[3]` is adopted on a tally that does not carry (2 for, 3 against).
 * That is not a mistake in the fixture. `outcomeDivergesFromTally` exists to
 * flag exactly that shape, and a dataset where outcome always matches arithmetic
 * leaves the one surface built to catch a governance error with nothing to
 * catch. It is labelled in its own body so nobody reads it as an accident.
 */
export const RESOLUTIONS: Resolution[] = [
  {
    id: RESOLUTION[0], decision_id: DECISION[0], title: "Resolution 26/04 — FY27 budget",
    body: "RESOLVED that the operating budget for FY27 as circulated be and is hereby approved.",
    status: "adopted", signing_state: "not_applicable", version_no: 1,
    superseded_by_id: null, adopted_at: "2026-07-15T14:35:00Z", version: 2,
    created_at: "2026-07-15T14:25:00Z", updated_at: "2026-07-15T14:35:00Z",
    workspace_id: DEMO_WORKSPACE_ID,
    votes: [
      vote(0, RESOLUTION[0], MEMBER[0], "for"),
      vote(1, RESOLUTION[0], MEMBER[1], "for"),
      vote(2, RESOLUTION[0], MEMBER[2], "recused"),
      vote(3, RESOLUTION[0], MEMBER[4], "abstain"),
    ],
  },
  {
    id: RESOLUTION[1], decision_id: DECISION[1], title: "Resolution 26/05 — Series B subscription",
    body: "RESOLVED that the Company enter into the subscription agreement on the terms circulated.",
    status: "draft", signing_state: "not_applicable", version_no: 1,
    superseded_by_id: null, adopted_at: null, version: 1,
    created_at: "2026-08-05T16:45:00Z", updated_at: "2026-08-05T16:45:00Z",
    workspace_id: DEMO_WORKSPACE_ID,
    votes: [],
  },
  {
    id: RESOLUTION[2], decision_id: DECISION[3], title: "Resolution 26/03 — São Paulo office",
    body: "RESOLVED that the Company establish a subsidiary in Brazil. Superseded by 26/06.",
    status: "superseded", signing_state: "not_applicable", version_no: 1,
    superseded_by_id: RESOLUTION[3], adopted_at: null, version: 3,
    created_at: "2026-07-15T15:00:00Z", updated_at: "2026-08-05T16:10:00Z",
    workspace_id: DEMO_WORKSPACE_ID,
    votes: [],
  },
  {
    id: RESOLUTION[3], decision_id: DECISION[5], title: "Resolution 26/07 — risk appetite (tally does not carry)",
    body:
      "RESOLVED that the revised risk appetite statement be adopted. NOTE: this fixture " +
      "is recorded as adopted on 2 for and 3 against so that the divergence check on the " +
      "resolutions surface has something to flag. It is a deliberate inconsistency.",
    status: "adopted", signing_state: "not_applicable", version_no: 2,
    superseded_by_id: null, adopted_at: "2026-09-02T09:40:00Z", version: 1,
    created_at: "2026-09-02T09:30:00Z", updated_at: "2026-09-02T09:40:00Z",
    workspace_id: DEMO_WORKSPACE_ID,
    votes: [
      vote(4, RESOLUTION[3], MEMBER[0], "against"),
      vote(5, RESOLUTION[3], MEMBER[1], "for"),
      vote(6, RESOLUTION[3], MEMBER[2], "against"),
      vote(7, RESOLUTION[3], MEMBER[3], "for"),
      vote(8, RESOLUTION[3], MEMBER[4], "against"),
    ],
  },
];

const update = (n: number, commitment: string, note: string, status: CommitmentUpdate["new_status"], member: string | null, at: string): CommitmentUpdate => ({
  id: UPDATE[n], commitment_id: commitment, note, new_status: status,
  author_board_member_id: member, created_at: at, workspace_id: DEMO_WORKSPACE_ID,
});

/**
 * Seven commitments covering every `CommitmentStatus` and every
 * `DeliveryStatus`.
 *
 * Two are overdue against 2026-09-02 and one has a null due date, which is what
 * `isOverdue` and the `/prepare` signals branch on. `delivery_status: "failed"`
 * appears once — the dashboard renders it differently from `not_dispatched`,
 * and the two are easy to conflate in a set that only ever shows one.
 */
export const COMMITMENTS: Commitment[] = [
  {
    id: COMMITMENT[0], decision_id: DECISION[0], resolution_id: RESOLUTION[0],
    owner_board_member_id: MEMBER[1], accountable_team: "Finance",
    title: "Circulate the FY27 budget sensitivity case",
    detail: "Downside case at 70% of plan revenue.", due_date: "2026-08-15",
    status: "completed", completed_at: "2026-08-12T11:00:00Z",
    external_system: "jira", external_task_id: "FIN-402",
    delivery_status: "delivered", delivery_attempts: 1, version: 4,
    created_at: "2026-07-15T14:45:00Z", updated_at: "2026-08-12T11:00:00Z",
    workspace_id: DEMO_WORKSPACE_ID,
    updates: [
      update(0, COMMITMENT[0], "Draft shared with the audit committee.", "in_progress", MEMBER[1], "2026-08-01T09:00:00Z"),
      update(1, COMMITMENT[0], "Circulated to the full board.", "completed", MEMBER[1], "2026-08-12T11:00:00Z"),
    ],
  },
  {
    // Overdue against 2026-09-02.
    id: COMMITMENT[1], decision_id: DECISION[1], resolution_id: null,
    owner_board_member_id: MEMBER[0], accountable_team: "Legal",
    title: "Close the remaining Series B conditions precedent",
    detail: "Three CPs outstanding: IP assignment, cap table, insurance.",
    due_date: "2026-08-29", status: "in_progress", completed_at: null,
    external_system: null, external_task_id: null,
    delivery_status: "not_dispatched", delivery_attempts: 0, version: 2,
    created_at: "2026-08-05T17:00:00Z", updated_at: "2026-08-28T14:00:00Z",
    workspace_id: DEMO_WORKSPACE_ID,
    updates: [
      update(2, COMMITMENT[1], "IP assignment signed; two remain.", null, MEMBER[0], "2026-08-28T14:00:00Z"),
    ],
  },
  {
    // Overdue and blocked — the shape `/prepare` surfaces first.
    id: COMMITMENT[2], decision_id: DECISION[1], resolution_id: null,
    owner_board_member_id: MEMBER[1], accountable_team: "Finance",
    title: "Deliver the audited FY26 accounts to the lead investor",
    detail: null, due_date: "2026-08-20", status: "blocked", completed_at: null,
    external_system: "jira", external_task_id: "FIN-418",
    delivery_status: "failed", delivery_attempts: 3, version: 3,
    created_at: "2026-08-05T17:02:00Z", updated_at: "2026-08-26T09:15:00Z",
    workspace_id: DEMO_WORKSPACE_ID,
    updates: [
      update(3, COMMITMENT[2], "Blocked on the auditor's revenue-recognition query.", "blocked", MEMBER[1], "2026-08-26T09:15:00Z"),
    ],
  },
  {
    id: COMMITMENT[3], decision_id: DECISION[4], resolution_id: null,
    owner_board_member_id: MEMBER[1], accountable_team: "People",
    title: "Scope the São Paulo sales hire plan",
    detail: "Four roles, phased over two quarters.", due_date: "2026-09-30",
    status: "open", completed_at: null,
    external_system: null, external_task_id: null,
    delivery_status: "pending", delivery_attempts: 1, version: 1,
    created_at: "2026-08-05T17:05:00Z", updated_at: "2026-08-05T17:05:00Z",
    workspace_id: DEMO_WORKSPACE_ID, updates: [],
  },
  {
    // No due date — `isOverdue` has to be false for reasons other than the date.
    id: COMMITMENT[4], decision_id: DECISION[2], resolution_id: null,
    owner_board_member_id: MEMBER[0], accountable_team: null,
    title: "Draw up a shortlist for the independent chair",
    detail: null, due_date: null, status: "open", completed_at: null,
    external_system: null, external_task_id: null,
    delivery_status: "not_dispatched", delivery_attempts: 0, version: 1,
    created_at: "2026-08-05T16:45:00Z", updated_at: "2026-08-05T16:45:00Z",
    workspace_id: DEMO_WORKSPACE_ID, updates: [],
  },
  {
    id: COMMITMENT[5], decision_id: DECISION[3], resolution_id: RESOLUTION[2],
    owner_board_member_id: MEMBER[4], accountable_team: "Operations",
    title: "Register the Brazilian subsidiary",
    detail: "Cancelled with the decision it came from.", due_date: "2026-09-15",
    status: "cancelled", completed_at: null,
    external_system: null, external_task_id: null,
    delivery_status: "not_dispatched", delivery_attempts: 0, version: 2,
    created_at: "2026-07-15T15:05:00Z", updated_at: "2026-08-05T16:10:00Z",
    workspace_id: DEMO_WORKSPACE_ID, updates: [],
  },
  {
    id: COMMITMENT[6], decision_id: DECISION[0], resolution_id: null,
    owner_board_member_id: MEMBER[4], accountable_team: "Company secretary",
    title: "File the FY27 budget resolution with the register",
    detail: null, due_date: "2026-09-12", status: "open", completed_at: null,
    external_system: null, external_task_id: null,
    delivery_status: "delivered", delivery_attempts: 1, version: 1,
    created_at: "2026-07-15T14:50:00Z", updated_at: "2026-07-15T14:50:00Z",
    workspace_id: DEMO_WORKSPACE_ID, updates: [],
  },
];

const packItem = (n: number, pack: string, doc: string, position: number, note: string | null): BoardPackItem => ({
  id: PACK_ITEM[n], board_pack_id: pack, document_id: doc, agenda_item_id: null,
  position, note, created_at: "2026-08-25T10:00:00Z", workspace_id: DEMO_WORKSPACE_ID,
});

/**
 * Three packs: a published one, its draft successor, and an unrelated draft.
 *
 * `withheld_items` is non-zero on the published pack. That number is the
 * clearance filter reporting what it removed, and it is the one figure on the
 * packs surface that is *about* the reader rather than about the pack — a
 * fixture set with zero everywhere would never show the "N items withheld"
 * line at all.
 */
export const PACKS: BoardPack[] = [
  {
    id: PACK[0], meeting_id: MEETING[0], title: "Q2 Board Pack",
    status: "published", version_no: 1, superseded_by_id: null,
    published_at: "2026-07-10T09:00:00Z", version: 3,
    created_at: "2026-07-08T15:00:00Z", updated_at: "2026-07-10T09:00:00Z",
    workspace_id: DEMO_WORKSPACE_ID,
    items: [
      packItem(0, PACK[0], DOCUMENT[0], 1, "Circulated five days ahead."),
      packItem(1, PACK[0], DOCUMENT[4], 2, null),
    ],
    withheld_items: 1,
  },
  {
    id: PACK[1], meeting_id: MEETING[2], title: "September Board Pack",
    status: "draft", version_no: 1, superseded_by_id: null,
    published_at: null, version: 2,
    created_at: "2026-08-25T10:00:00Z", updated_at: "2026-08-28T09:20:00Z",
    workspace_id: DEMO_WORKSPACE_ID,
    items: [
      packItem(2, PACK[1], DOCUMENT[3], 1, "Revised term sheet — supersedes the July draft."),
      packItem(3, PACK[1], DOCUMENT[5], 2, null),
      packItem(4, PACK[1], DOCUMENT[7], 3, "Q2 minutes, for approval."),
    ],
    withheld_items: 0,
  },
  {
    id: PACK[2], meeting_id: MEETING[3], title: "Audit Committee Pack",
    status: "draft", version_no: 1, superseded_by_id: null,
    published_at: null, version: 1,
    created_at: "2026-08-29T11:00:00Z", updated_at: "2026-08-29T11:00:00Z",
    workspace_id: DEMO_WORKSPACE_ID,
    items: [packItem(5, PACK[2], DOCUMENT[4], 1, null)],
    withheld_items: 2,
  },
];

/**
 * Three sets of minutes: a final one, the draft it superseded, and a draft for
 * a meeting still in progress.
 *
 * The superseded pair is what `minutes.current()` has to pick between, and the
 * in-progress one is the case `MINUTES_LOCKED_MEETING_STATUSES` allows editing
 * for while the scheduled and draft meetings do not.
 */
export const MINUTES_SET: Minutes[] = [
  {
    id: MINUTES[0], meeting_id: MEETING[0],
    body:
      "The Chair opened the meeting at 13:00. Apologies were received from Mr Farouk.\n\n" +
      "The FY27 operating budget was approved, with Ms Raghunathan recording her opposition " +
      "on the grounds that sales headcount is ahead of pipeline.\n\n" +
      "The meeting closed at 15:30.",
    status: "final", version_no: 2, superseded_by_id: null,
    finalised_at: "2026-07-17T09:00:00Z", version: 3,
    created_at: "2026-07-15T15:35:00Z", updated_at: "2026-07-17T09:00:00Z",
    workspace_id: DEMO_WORKSPACE_ID,
  },
  {
    id: MINUTES[1], meeting_id: MEETING[0],
    body: "First draft, superseded before circulation.",
    status: "draft", version_no: 1, superseded_by_id: MINUTES[0],
    finalised_at: null, version: 2,
    created_at: "2026-07-15T15:32:00Z", updated_at: "2026-07-16T10:00:00Z",
    workspace_id: DEMO_WORKSPACE_ID,
  },
  {
    id: MINUTES[2], meeting_id: MEETING[3],
    body: "In progress — the auditor's two management-letter points were taken first.",
    status: "draft", version_no: 1, superseded_by_id: null,
    finalised_at: null, version: 1,
    created_at: "2026-09-02T09:05:00Z", updated_at: "2026-09-02T09:40:00Z",
    workspace_id: DEMO_WORKSPACE_ID,
  },
];

/**
 * Three pending entity conflicts.
 *
 * This is the surface whose invented predecessor is the reason demo mode is
 * built the way it is — `GET /api/conflicts` 500ed for four days while the
 * dashboard reported "2 name conflicts awaiting your review" from a fallback
 * array. These three are fabricated too. The difference is that nothing here
 * can be reached without the banner also being on screen, and the seam that
 * serves them cannot be entered from a failed request.
 */
export const CONFLICTS: EntityConflict[] = [
  {
    id: CONFLICT[0], name_a: "Northwind Ventures", type_a: "ORGANIZATION",
    name_b: "Northwind Ventures LLP", type_b: "ORGANIZATION", similarity: 0.94,
    quote_a: "Northwind Ventures led the Series A.",
    quote_b: "The lead investor, Northwind Ventures LLP, waived its pre-emption right.",
    sensitivity: 1, status: "pending", created_at: "2026-08-31T17:06:00Z",
  },
  {
    id: CONFLICT[1], name_a: "Tomás Lindqvist", type_a: "PERSON",
    name_b: "Tomas Lindquist", type_b: "PERSON", similarity: 0.89,
    quote_a: "Tomás Lindqvist joined as an observer in March.",
    quote_b: "Apologies were received from Tomas Lindquist.",
    sensitivity: 2, status: "pending", created_at: "2026-07-15T16:05:00Z",
  },
  {
    id: CONFLICT[2], name_a: "the audit committee", type_a: "GROUP",
    name_b: "Audit & Risk Committee", type_b: "GROUP", similarity: 0.71,
    quote_a: "referred to the audit committee for review",
    quote_b: "The Audit & Risk Committee met on 2 September.",
    sensitivity: 0, status: "pending", created_at: "2026-09-02T09:10:00Z",
  },
];
