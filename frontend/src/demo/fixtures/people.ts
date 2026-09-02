import type { BoardMember } from "@/lib/board-members";
import { DEMO_WORKSPACE_ID, MEMBER } from "./ids";

/**
 * The demo board.
 *
 * These *are* plausible people, unlike the demo principal, and that is a
 * deliberate difference. A board table with six rows reading "DEMO 1"…"DEMO 6"
 * tells you nothing about whether the surface handles a long name, a missing
 * organization, or a recused member — which is the entire question the
 * maintainer is opening these pages to answer. The honesty guarantee is carried
 * by the banner and by the workspace id, once, at the top of the screen, rather
 * than by degrading every row underneath it.
 *
 * `principal_id` is null on all six: none of them is the signed-in demo
 * principal, and pointing one at it would imply a membership row that the
 * fixture set does not otherwise model.
 */
export const BOARD_MEMBERS: BoardMember[] = [
  {
    id: MEMBER[0], workspace_id: DEMO_WORKSPACE_ID, principal_id: null,
    full_name: "Amara Okonkwo", organization: "Northwind Ventures",
    role: "director", contact_email: "amara@northwind.example", voting: "voting",
    active: true, version: 3,
    created_at: "2026-01-12T09:00:00Z", updated_at: "2026-06-02T14:20:00Z",
  },
  {
    id: MEMBER[1], workspace_id: DEMO_WORKSPACE_ID, principal_id: null,
    full_name: "Daniel Reyes", organization: null,
    role: "executive", contact_email: "daniel@example.com", voting: "voting",
    active: true, version: 5,
    created_at: "2025-11-03T09:00:00Z", updated_at: "2026-08-11T10:05:00Z",
  },
  {
    id: MEMBER[2], workspace_id: DEMO_WORKSPACE_ID, principal_id: null,
    full_name: "Priya Raghunathan", organization: "Kestrel Capital",
    role: "director", contact_email: "priya@kestrel.example", voting: "recused",
    active: true, version: 2,
    created_at: "2026-02-20T09:00:00Z", updated_at: "2026-08-05T16:40:00Z",
  },
  {
    id: MEMBER[3], workspace_id: DEMO_WORKSPACE_ID, principal_id: null,
    full_name: "Tomás Lindqvist", organization: "Meridian Growth Partners",
    role: "observer", contact_email: null, voting: "non_voting",
    active: true, version: 1,
    created_at: "2026-03-14T09:00:00Z", updated_at: "2026-03-14T09:00:00Z",
  },
  {
    id: MEMBER[4], workspace_id: DEMO_WORKSPACE_ID, principal_id: null,
    full_name: "Grace Chen", organization: null,
    role: "administrator", contact_email: "grace@example.com", voting: "non_voting",
    active: true, version: 4,
    created_at: "2025-11-03T09:00:00Z", updated_at: "2026-07-19T11:30:00Z",
  },
  {
    // Inactive on purpose: `boardMembersApi.list` defaults to `active=true`, so a
    // dataset with no inactive member cannot show that the filter does anything.
    id: MEMBER[5], workspace_id: DEMO_WORKSPACE_ID, principal_id: null,
    full_name: "Ibrahim Farouk", organization: "Farouk Advisory",
    role: "adviser", contact_email: "ibrahim@farouk.example", voting: "non_voting",
    active: false, version: 2,
    created_at: "2025-12-01T09:00:00Z", updated_at: "2026-05-30T08:00:00Z",
  },
];
