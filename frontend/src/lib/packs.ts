import type { BadgeTone } from "@/components/ui/badge";
import { __unfilteredDocuments, type Document } from "@/lib/documents";

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

// --- Mock store ------------------------------------------------------------

const WS = "00000000-0000-0000-0000-000000000001";

type StoredItem = Omit<BoardPackItem, "position"> & { position: number };

/**
 * Packs as the server stores them: every item, at its stored position, with no
 * clearance predicate applied. Nothing outside `packsApi` may read this.
 *
 * The Q3 pack is the interesting one — it mixes investor, internal,
 * confidential, and restricted documents, so the same pack looks different to
 * every clearance level and the withholding path is exercised by default rather
 * than by a special case.
 */
const storedPacks: (Omit<BoardPack, "items"> & { items: StoredItem[] })[] = [
  {
    id: "pack-q3-v2",
    meeting_id: "m-q3",
    title: "Q3 FY26 board pack",
    status: "published",
    version_no: 2,
    superseded_by_id: null,
    published_at: "2026-07-14T09:00:00Z",
    version: 4,
    created_at: "2026-07-13T11:00:00Z",
    updated_at: "2026-07-14T09:00:00Z",
    workspace_id: WS,
    items: [
      {
        id: "pi-q3-1",
        board_pack_id: "pack-q3-v2",
        document_id: "doc-q3-deck",
        agenda_item_id: "b1",
        position: 1,
        note: "Circulated ahead of the session.",
        created_at: "2026-07-13T11:05:00Z",
        workspace_id: WS,
      },
      {
        id: "pi-q3-2",
        board_pack_id: "pack-q3-v2",
        document_id: "doc-comp",
        agenda_item_id: null,
        position: 2,
        note: null,
        created_at: "2026-07-13T11:06:00Z",
        workspace_id: WS,
      },
      {
        id: "pi-q3-3",
        board_pack_id: "pack-q3-v2",
        document_id: "doc-kpi",
        agenda_item_id: "b2",
        position: 3,
        note: "Read alongside the forecast item.",
        created_at: "2026-07-13T11:07:00Z",
        workspace_id: WS,
      },
      {
        id: "pi-q3-4",
        board_pack_id: "pack-q3-v2",
        document_id: "doc-seriesb-term",
        agenda_item_id: "b3",
        position: 4,
        note: null,
        created_at: "2026-07-13T11:08:00Z",
        workspace_id: WS,
      },
      {
        id: "pi-q3-5",
        board_pack_id: "pack-q3-v2",
        document_id: "doc-pricing-memo",
        agenda_item_id: "b3",
        position: 5,
        note: null,
        created_at: "2026-07-13T11:09:00Z",
        workspace_id: WS,
      },
    ],
  },
  {
    id: "pack-q3-v1",
    meeting_id: "m-q3",
    title: "Q3 FY26 board pack",
    status: "published",
    version_no: 1,
    superseded_by_id: "pack-q3-v2",
    published_at: "2026-07-11T16:30:00Z",
    version: 3,
    created_at: "2026-07-11T10:00:00Z",
    updated_at: "2026-07-13T11:00:00Z",
    workspace_id: WS,
    items: [
      {
        id: "pi-q3v1-1",
        board_pack_id: "pack-q3-v1",
        document_id: "doc-q3-deck",
        agenda_item_id: null,
        position: 1,
        note: null,
        created_at: "2026-07-11T10:05:00Z",
        workspace_id: WS,
      },
      {
        id: "pi-q3v1-2",
        board_pack_id: "pack-q3-v1",
        document_id: "doc-kpi",
        agenda_item_id: null,
        position: 2,
        note: null,
        created_at: "2026-07-11T10:06:00Z",
        workspace_id: WS,
      },
    ],
  },
  {
    id: "pack-m14",
    meeting_id: "m-14",
    title: "Board Meeting 14 pre-read",
    status: "published",
    version_no: 1,
    superseded_by_id: null,
    published_at: "2026-07-08T17:00:00Z",
    version: 5,
    created_at: "2026-07-07T09:00:00Z",
    updated_at: "2026-07-08T17:00:00Z",
    workspace_id: WS,
    items: [
      {
        id: "pi-m14-1",
        board_pack_id: "pack-m14",
        document_id: "doc-runway",
        agenda_item_id: "a1",
        position: 1,
        note: "Three scenarios; the middle one is the planning case.",
        created_at: "2026-07-07T09:10:00Z",
        workspace_id: WS,
      },
      {
        id: "pi-m14-2",
        board_pack_id: "pack-m14",
        document_id: "doc-hiring",
        agenda_item_id: "a3",
        position: 2,
        note: null,
        created_at: "2026-07-07T09:11:00Z",
        workspace_id: WS,
      },
      {
        id: "pi-m14-3",
        board_pack_id: "pack-m14",
        document_id: "doc-pricing-memo",
        agenda_item_id: "a2",
        position: 3,
        note: null,
        created_at: "2026-07-07T09:12:00Z",
        workspace_id: WS,
      },
    ],
  },
  {
    id: "pack-seq",
    meeting_id: "m-seq",
    title: "Series B session — pre-read",
    status: "draft",
    version_no: 1,
    superseded_by_id: null,
    published_at: null,
    version: 2,
    created_at: "2026-07-18T14:00:00Z",
    updated_at: "2026-07-18T14:30:00Z",
    workspace_id: WS,
    items: [
      {
        id: "pi-seq-1",
        board_pack_id: "pack-seq",
        document_id: "doc-seriesb-term",
        agenda_item_id: null,
        position: 1,
        note: "Draft four. Preference stack still open.",
        created_at: "2026-07-18T14:10:00Z",
        workspace_id: WS,
      },
    ],
  },
];

/**
 * The clearance filter, ported from `_fetch_items_for_packs`
 * (`meridian/packs.py:153-190`).
 *
 * This runs inside the mock's *server* boundary. It is not a UI concern and must
 * never migrate into a component: at P3 this function disappears entirely,
 * replaced by the WHERE clause it imitates. If a component ever needs to know a
 * document's sensitivity to decide what to draw, the filtering has leaked into
 * the client and the invariant is broken.
 *
 * Renumbering is the second half of the contract. Rows are taken in stored
 * order and re-emitted at 1..N, so a caller cannot see where a row was removed.
 */
function visibleItems(items: StoredItem[], clearance: number): BoardPackItem[] {
  const sensitivityById = new Map(__unfilteredDocuments.map((d) => [d.id, d.sensitivity]));
  const out: BoardPackItem[] = [];
  for (const item of [...items].sort((a, b) => a.position - b.position)) {
    const sensitivity = sensitivityById.get(item.document_id);
    // An item whose document cannot be found is dropped rather than shown. The
    // server-side JOIN behaves the same way: no document row, no item row.
    if (sensitivity === undefined || sensitivity > clearance) continue;
    out.push({ ...item, position: out.length + 1 });
  }
  return out;
}

function serialise(
  stored: (typeof storedPacks)[number],
  clearance: number,
): BoardPack {
  const { items, ...rest } = stored;
  return structuredClone({ ...rest, items: visibleItems(items, clearance) });
}

const delay = (ms = 400) => new Promise((r) => setTimeout(r, ms));

/**
 * Mocked Meridian board-pack API.
 *
 * Method names and arguments follow `meridian/packs.py` so the P3 swap is
 * mechanical. `clearance` is required on every read for the same reason it is
 * required in the Python: there is no such thing as an unfiltered read of a pack.
 *
 * Ordering matches `list_packs`: `version_no DESC, created_at DESC`.
 */
export const packsApi = {
  async list(opts: {
    clearance: number;
    meeting_id?: string;
    status?: PackStatus;
  }): Promise<BoardPack[]> {
    await delay();
    return storedPacks
      .filter((p) => (opts.meeting_id ? p.meeting_id === opts.meeting_id : true))
      .filter((p) => (opts.status ? p.status === opts.status : true))
      .slice()
      .sort(
        (a, b) =>
          b.version_no - a.version_no || b.created_at.localeCompare(a.created_at),
      )
      .map((p) => serialise(p, opts.clearance));
  },

  async get(id: string, opts: { clearance: number }): Promise<BoardPack | null> {
    await delay(200);
    const p = storedPacks.find((x) => x.id === id);
    return p ? serialise(p, opts.clearance) : null;
  },
};
