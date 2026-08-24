import type { BadgeTone } from "@/components/ui/badge";
import { apiGet, apiGetOrNull } from "@/lib/http";
import type { Document } from "@/lib/documents";

/**
 * Board packs — the pre-read package circulated before a meeting.
 *
 * Like `decisions.ts`, this mirrors a backend contract that EXISTS:
 * `meridian/packs.py` and migration `0010_board_pack`, merged in PR #33. Field
 * names are snake_case and match the Python dataclasses one for one, so wiring
 * this to the real API at P3 is a swap of the `packsApi` object and nothing else.
 *
 * Where this file and `meridian/packs.py` disagree, the Python is right.
 *
 * ---------------------------------------------------------------------------
 * TWO CONTRACT PROPERTIES THIS SURFACE MUST NOT BREAK
 * ---------------------------------------------------------------------------
 *
 * 1. **Items are clearance-filtered and renumbered by the server.**
 *    `_fetch_items_for_packs` (`meridian/packs.py:153-190`) pushes the clearance
 *    predicate into the WHERE clause and then renumbers the surviving rows from
 *    1, so what the caller receives is always contiguous. The reason is in that
 *    docstring: an investor shown items at positions [2, 3] learns a position 1
 *    exists and can count the holes, which is the same disclosure as a
 *    placeholder, only quieter.
 *
 *    The consequence for the UI is absolute: **there is no withheld count to
 *    render, and none may be derived.** No gaps, no placeholders, no "N items
 *    hidden", no subtracting a visible length from a total. The pack read model
 *    carries no total, and that absence is deliberate — do not add one.
 *
 * 2. **`position` is a display ordinal, not an identifier.** It is renumbered
 *    per caller, so two readers of the same pack see different numbers on the
 *    same row. Every reference to an item — keys, selection, reordering — uses
 *    `id`. `reorder_pack_items` takes item IDs for exactly this reason.
 */

// --- Status ----------------------------------------------------------------

/** `meridian/packs.py:39-42`. A pack is draft or published; there is no third state. */
export type PackStatus = "draft" | "published";

export const PACK_STATUS_LABEL: Record<PackStatus, string> = {
  draft: "Draft",
  published: "Published",
};

export const PACK_STATUS_TONE: Record<PackStatus, BadgeTone> = {
  draft: "neutral",
  published: "success",
};

export const PACK_STATUS_DOT: Record<PackStatus, string> = {
  draft: "bg-muted-foreground",
  published: "bg-success",
};

export const PACK_STATUSES = Object.keys(PACK_STATUS_LABEL) as PackStatus[];

/**
 * Meeting statuses that lock a pack against mutation, from
 * `_LOCKED_MEETING_STATUSES` (`meridian/packs.py:45`).
 *
 * Deliberately typed as a plain string set rather than reusing
 * `MeetingStatus` from `lib/meetings.ts`: that mock declares `review` and
 * `archived`, which `meridian/meetings.py` has never had, and omits `cancelled`,
 * which it does have. Binding this to it would import that divergence into a
 * lock rule. Tracked separately — see the PR.
 */
export const PACK_LOCKED_MEETING_STATUSES: ReadonlySet<string> = new Set([
  "in_progress",
  "completed",
  "cancelled",
]);

// --- Read models -----------------------------------------------------------

/**
 * Mirrors the `BoardPackItem` dataclass (`meridian/packs.py:78-88`).
 *
 * Note what is *not* here: no title, no sensitivity, no document body. The item
 * is a reference. Resolving `document_id` to something a human can read is the
 * caller's job, and that resolution is itself clearance-gated.
 */
export type BoardPackItem = {
  id: string;
  board_pack_id: string;
  document_id: string;
  agenda_item_id: string | null;
  /** Caller-relative display ordinal, 1..N contiguous. NOT an identifier. */
  position: number;
  note: string | null;
  created_at: string; // ISO
  workspace_id: string;
};

/** Mirrors the `BoardPack` dataclass (`meridian/packs.py:90-103`). */
export type BoardPack = {
  id: string;
  meeting_id: string;
  title: string;
  status: PackStatus;
  /** Published-artifact lineage. Distinct from `version` — see CONTRIBUTING.md. */
  version_no: number;
  /** Set when this pack was replaced; points at its replacement. */
  superseded_by_id: string | null;
  published_at: string | null; // ISO
  /** Optimistic-concurrency counter, not a published-version number. */
  version: number;
  created_at: string; // ISO
  updated_at: string; // ISO
  workspace_id: string;
  /** Only the items this caller may read, renumbered from 1. */
  items: BoardPackItem[];
  /**
   * How many items this caller may NOT read. A count and nothing else — never a title,
   * an id, a date, or a position (ADR-018).
   *
   * A published pack claims to be *the material for this meeting*, so a director who
   * prepares from one that silently dropped three items walks in believing they are
   * prepared. Render it; do not treat a non-zero value as an error state.
   */
  withheld_items: number;
};

// --- Derived helpers -------------------------------------------------------

/**
 * True when the pack can still be edited.
 *
 * Mirrors the two guards every mutating operation in `packs.py` applies: the
 * pack must be `draft`, and the parent meeting must not be in a locked status.
 * This is a *hint for disabling controls*, not an authorisation check — the
 * server enforces both regardless of what the UI renders.
 */
export function isEditable(pack: BoardPack, meetingStatus: string | undefined): boolean {
  if (pack.status !== "draft") return false;
  if (meetingStatus === undefined) return false;
  return !PACK_LOCKED_MEETING_STATUSES.has(meetingStatus);
}

/**
 * Follows `superseded_by_id` to the pack that replaced this one.
 *
 * Returns `null` rather than throwing when the target is absent: a reader may
 * hold a pack whose replacement they are not cleared to see, and a missing link
 * is a legitimate state, not an error. Same reasoning as `supersededBy` in
 * `decisions.ts`.
 */
export function supersededBy(pack: BoardPack, all: BoardPack[]): BoardPack | null {
  if (!pack.superseded_by_id) return null;
  return all.find((p) => p.id === pack.superseded_by_id) ?? null;
}

/**
 * Pairs each readable item with its document.
 *
 * A `null` document means the row could not be resolved — the reference is
 * dangling, not withheld. Withheld items never reach this function; the server
 * dropped them before the pack was serialised. The distinction matters because
 * rendering "unavailable" for a dangling reference would fabricate a hidden
 * document that does not exist.
 */
export function resolveItems(
  items: BoardPackItem[],
  documents: Document[],
): { item: BoardPackItem; document: Document | null }[] {
  const byId = new Map(documents.map((d) => [d.id, d]));
  return items.map((item) => ({ item, document: byId.get(item.document_id) ?? null }));
}

// --- API client ------------------------------------------------------------

/**
 * Meridian board-pack API. Live as of CP-C; the in-memory mock is gone, and with it
 * the function that imitated `_fetch_items_for_packs` inside the client.
 *
 * **`clearance` is no longer an argument, and that is the point.** The mock took one
 * because it had to filter its own data; the real API resolves it from the caller's
 * active membership on every request (ADR-013). A client able to name its own
 * clearance could ask for every restricted document in the workspace, so there is
 * deliberately nowhere to pass one — and the OpenAPI guard fails the build if an
 * endpoint ever offers the option.
 *
 * The two properties the surface depends on are the server's, unchanged: items are
 * filtered then renumbered from 1, so a withheld item leaves no gap; and `position`
 * is a per-caller ordinal rather than an identity.
 */
export const packsApi = {
  async list(opts: { meeting_id: string; status?: PackStatus }): Promise<BoardPack[]> {
    return apiGet<BoardPack[]>("/packs", {
      meeting_id: opts.meeting_id,
      status: opts.status,
    });
  },

  async get(id: string): Promise<BoardPack | null> {
    return apiGetOrNull<BoardPack>(`/packs/${encodeURIComponent(id)}`);
  },
};
