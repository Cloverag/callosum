import type { BoardMember } from "@/lib/board-members";

/**
 * Board-directory fixtures for the frontend unit tests.
 *
 * These were the `mockMembers` store inside `lib/board-members.ts` until CP-C
 * replaced it with a real API client. Kept because the assertions they support are
 * contract assertions — no clearance field, a director with no login, an inactive
 * member who must still resolve — and those hold whether the bytes come from a mock
 * or from Postgres.
 *
 * **Not shipped.** Nothing under `src/` imports this.
 *
 * Ids match the `board_member_id` values in the resolutions and commitments
 * fixtures, so the cross-module "every vote resolves to a real director" assertions
 * still work.
 */

const WS = "00000000-0000-0000-0000-000000000001";

export const BOARD_MEMBER_FIXTURES: BoardMember[] = [
  {
    id: "bm-raj",
    workspace_id: WS,
    principal_id: "p-raj",
    full_name: "Raj Malhotra",
    organization: "Meridian",
    role: "executive",
    contact_email: "raj@meridian.example",
    voting: "voting",
    active: true,
    version: 1,
    created_at: "2026-01-12T09:00:00Z",
    updated_at: "2026-01-12T09:00:00Z",
  },
  {
    id: "bm-priya",
    workspace_id: WS,
    principal_id: "p-priya",
    full_name: "Priya Nair",
    organization: "Meridian",
    role: "executive",
    contact_email: "priya@meridian.example",
    voting: "voting",
    active: true,
    version: 1,
    created_at: "2026-01-12T09:00:00Z",
    updated_at: "2026-01-12T09:00:00Z",
  },
  {
    id: "bm-marcus",
    workspace_id: WS,
    principal_id: null,
    full_name: "Marcus Webb",
    organization: "Arbor Capital",
    role: "director",
    contact_email: "m.webb@arbor.example",
    voting: "voting",
    active: true,
    version: 1,
    created_at: "2026-01-14T09:00:00Z",
    updated_at: "2026-01-14T09:00:00Z",
  },
  {
    id: "bm-elena",
    workspace_id: WS,
    principal_id: null,
    full_name: "Elena Fischer",
    organization: "Northlight Ventures",
    role: "director",
    contact_email: "elena@northlight.example",
    voting: "voting",
    active: true,
    version: 1,
    created_at: "2026-02-02T09:00:00Z",
    updated_at: "2026-02-02T09:00:00Z",
  },
  {
    id: "bm-tobi",
    workspace_id: WS,
    principal_id: null,
    full_name: "Tobi Adeyemi",
    organization: "Arbor Capital",
    role: "observer",
    contact_email: null,
    voting: "non_voting",
    active: true,
    version: 1,
    created_at: "2026-03-09T09:00:00Z",
    updated_at: "2026-03-09T09:00:00Z",
  },
  {
    id: "bm-hannah",
    workspace_id: WS,
    principal_id: null,
    full_name: "Hannah Vogel",
    organization: "Vogel & Co",
    role: "adviser",
    contact_email: null,
    voting: "non_voting",
    active: false,
    version: 2,
    created_at: "2026-01-20T09:00:00Z",
    updated_at: "2026-06-30T09:00:00Z",
  },
];
