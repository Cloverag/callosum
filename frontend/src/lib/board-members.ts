import type { BadgeTone } from "@/components/ui/badge";
import { apiGet, apiGetOrNull } from "@/lib/http";

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

// --- API client ------------------------------------------------------------

/**
 * Meridian board-directory API.
 *
 * Live as of CP-C; the in-memory mock this replaced is gone.
 *
 * **`active` is a tri-state, and this is a contract correction.** The mock exposed
 * `include_inactive?: boolean`, which `meridian/board_members.py` has never had — the
 * domain takes `active: bool | None = True`, meaning active-only by default, `false`
 * for departed members only, and "all" for everyone. The two-valued flag silently
 * dropped the inactive-only case, and inventing a parameter the backend cannot honour
 * is the same defect as inventing a status it cannot produce.
 *
 * `role` was missing from the mock entirely and is a filter the domain supports.
 */
export const boardMembersApi = {
  async list(opts?: {
    /** `true` (default) active only · `false` departed only · `"all"` everyone. */
    active?: boolean | "all";
    role?: BoardRole;
  }): Promise<BoardMember[]> {
    const active = opts?.active ?? true;
    return apiGet<BoardMember[]>("/board-members", {
      active: active === "all" ? "all" : String(active),
      role: opts?.role,
    });
  },

  async get(id: string): Promise<BoardMember | null> {
    // `null` for a missing member, preserving the mock's contract. Note the domain
    // returns INACTIVE members here on purpose: historical votes resolve through this
    // lookup, and a departed director must not become unresolvable.
    return apiGetOrNull<BoardMember>(`/board-members/${encodeURIComponent(id)}`);
  },
};
