import type { BadgeTone } from "@/components/ui/badge";

/**
 * The board directory — who participates, in what capacity.
 *
 * Mirrors `meridian/board_members.py` and migration `0012_board_member` (PR #42),
 * following the pattern `decisions.ts` established: snake_case fields matching the
 * Python dataclass one for one, so the P3 swap is the `boardMembersApi` object and
 * nothing else.
 *
 * Where this file and `meridian/board_members.py` disagree, the Python is right.
 *
 * ---------------------------------------------------------------------------
 * THIS IS NOT `membership`, AND THE UI MUST NOT CONFLATE THEM
 * ---------------------------------------------------------------------------
 * `membership` is the auth fact — principal × workspace → role, clearance — and it
 * requires a login. This is the governance directory: a non-executive director who
 * never signs in is still recordable, votable, and assignable. Hence `principal_id`
 * is nullable, and its absence is not a defect to surface as a warning.
 *
 * There is deliberately **no clearance field here**. Clearance belongs to
 * `membership`; two sources of truth for clearance is how RBAC gets bypassed. If a
 * surface ever needs a member's clearance, that is a backend question, not a column
 * to add to this type.
 */

/** `meridian/board_members.py:38-42`. FR-WS-02. */
export type BoardRole = "director" | "observer" | "executive" | "administrator" | "adviser";

export const BOARD_ROLE_LABEL: Record<BoardRole, string> = {
  director: "Director",
  observer: "Observer",
  executive: "Executive",
  administrator: "Administrator",
  adviser: "Adviser",
};

/**
 * `meridian/board_members.py:46-48`. FR-WS-03 calls this "voting status".
 *
 * An enum rather than a boolean because `recused` is a real third state, not an
 * absence of voting rights. This is the member's **standing** status — recusal from
 * a single motion is a property of the vote, and lives on `resolution_vote`.
 */
export type VotingStatus = "voting" | "non_voting" | "recused";

export const VOTING_STATUS_LABEL: Record<VotingStatus, string> = {
  voting: "Voting",
  non_voting: "Non-voting",
  recused: "Recused",
};

export const VOTING_STATUS_TONE: Record<VotingStatus, BadgeTone> = {
  voting: "success",
  non_voting: "neutral",
  recused: "warning",
};

/** Mirrors the `BoardMember` dataclass (`meridian/board_members.py:81-95`). */
export type BoardMember = {
  id: string;
  workspace_id: string;
  /** NULL when this person has no login. Not a defect — see the note above. */
  principal_id: string | null;
  full_name: string;
  organization: string | null;
  role: BoardRole;
  contact_email: string | null;
  voting: VotingStatus;
  active: boolean;
  version: number;
  created_at: string; // ISO
  updated_at: string; // ISO
};

// --- Derived helpers -------------------------------------------------------

/**
 * Resolves a member id to a display name.
 *
 * Returns `null` rather than a placeholder when the member is not in the set: the
 * caller decides how to render an unresolved reference, and inventing "Unknown
 * director" here would put a fabricated person on screen.
 */
export function nameOf(id: string | null, members: BoardMember[]): string | null {
  if (!id) return null;
  return members.find((m) => m.id === id)?.full_name ?? null;
}

/** Initials for an avatar, from the first and last word of a name. */
export function initialsOf(fullName: string): string {
  const parts = fullName.trim().split(/\s+/);
  if (parts.length === 0) return "?";
  const first = parts[0][0] ?? "";
  const last = parts.length > 1 ? (parts[parts.length - 1][0] ?? "") : "";
  return (first + last).toUpperCase();
}

// --- Mock store ------------------------------------------------------------

const WS = "00000000-0000-0000-0000-000000000001";

/**
 * The fictional Meridian board.
 *
 * Names match the directors quoted in `decisions.ts` and `minutes.ts` so the three
 * surfaces describe one company rather than three. The mix is deliberate: a
 * non-voting observer, an adviser with no login, and a deactivated member, because
 * each of those is a state the domain allows and a surface has to handle.
 */
const mockMembers: BoardMember[] = [
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

const clone = (m: BoardMember): BoardMember => structuredClone(m);
const delay = (ms = 300) => new Promise((r) => setTimeout(r, ms));

/**
 * Mocked Meridian board-directory API.
 *
 * Method names follow `meridian/board_members.py`. `list_members` returns active
 * members by default — the domain rule is deactivate-never-delete, so an inactive
 * director is history rather than a deletion, and surfacing them by default would
 * put departed people in every picker.
 */
export const boardMembersApi = {
  async list(opts?: { include_inactive?: boolean }): Promise<BoardMember[]> {
    await delay();
    return mockMembers
      .filter((m) => (opts?.include_inactive ? true : m.active))
      .slice()
      .sort((a, b) => a.full_name.localeCompare(b.full_name))
      .map(clone);
  },

  async get(id: string): Promise<BoardMember | null> {
    await delay(150);
    const m = mockMembers.find((x) => x.id === id);
    return m ? clone(m) : null;
  },
};
