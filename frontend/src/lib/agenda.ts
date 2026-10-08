import { apiDelete, apiGet, apiGetOrNull, apiPatch, apiPost } from "@/lib/http";

/**
 * Agenda items — what a meeting will actually work through.
 *
 * Mirrors `meridian/agenda.py` and migration `0008_agenda_item` (CP2). **A separate
 * module because agenda is a separate aggregate**: `Meeting` has no `agenda` field in
 * the domain, and the array the meetings mock carried was an invention that let two
 * surfaces render agenda without anything to fetch it from.
 *
 * The mock's shape was wrong in three ways beyond that, all corrected here:
 *
 *   mock `order`        -> `position`          (the domain's name, 1-indexed)
 *   mock `timeboxMins`  -> `duration_minutes`  (camelCase in a snake_case contract)
 *   mock (absent)       -> `description`, `meeting_id`, `version`, timestamps
 *
 * `position` is 1-indexed and contiguous within a meeting. Unlike board-pack items it
 * is **not** renumbered per caller — agenda is not clearance-filtered — so it is a
 * stable ordinal here. It is still not an identity: `id` is.
 */
export type AgendaItem = {
  id: string;
  meeting_id: string;
  workspace_id: string;
  title: string;
  description: string | null;
  /** Timebox in minutes. Null when the item is untimed. */
  duration_minutes: number | null;
  /** Free text — the domain has no board-member link on agenda items. */
  presenter: string | null;
  /** 1-indexed display order within the meeting. */
  position: number;
  /** Optimistic-concurrency counter. */
  version: number;
  created_at: string; // ISO
  updated_at: string; // ISO
};

/** Total timebox in minutes, ignoring untimed items. */
export function totalMinutes(items: AgendaItem[]): number {
  return items.reduce((sum, item) => sum + (item.duration_minutes ?? 0), 0);
}

/** Items with a named presenter — "who is actually bringing this". */
export function withPresenter(items: AgendaItem[]): AgendaItem[] {
  return items.filter((item) => item.presenter !== null && item.presenter.trim() !== "");
}

/**
 * A new agenda item.
 *
 * Mirrors `AgendaItemCreate` in `meridian/api/agenda.py`, which sets
 * `extra="forbid"` — an unrecognised field is a 422, not a silently dropped one, so
 * this type has to stay honest rather than merely close.
 *
 * `position` is omitted to append. Supplying one *inserts* and shifts everything after
 * it, which is why the API takes it at create rather than as a later PATCH: an insert
 * is a reordering of the whole tail.
 *
 * There is no `workspace_id`. The API derives it from the session (ADR-013) and
 * `tests/test_openapi_input_guard.py` fails the build if an endpoint ever accepts one.
 */
export type AgendaItemCreate = {
  meeting_id: string;
  title: string;
  description?: string | null;
  duration_minutes?: number | null;
  presenter?: string | null;
  position?: number | null;
};

/**
 * Changes to an existing item. Mirrors `AgendaItemPatch` (`extra="forbid"`).
 *
 * `expected_version` is required: two people editing one agenda is the ordinary case
 * the week before a board meeting, and a 409 beats silently keeping whichever save
 * landed last. `null` clears a field, while an omitted key leaves it untouched.
 */
export type AgendaItemPatch = {
  expected_version: number;
  title?: string;
  description?: string | null;
  duration_minutes?: number | null;
  presenter?: string | null;
};

export const agendaApi = {
  /** A meeting's agenda, in the server's `position ASC` order. */
  async list(meetingId: string): Promise<AgendaItem[]> {
    return apiGet<AgendaItem[]>("/agenda", { meeting_id: meetingId });
  },

  async get(id: string): Promise<AgendaItem | null> {
    return apiGetOrNull<AgendaItem>(`/agenda/${encodeURIComponent(id)}`);
  },

  /**
   * Appends an item to a meeting's agenda.
   *
   * No `expected_version`, and that is the contract rather than an omission: a create
   * has no prior version to be stale against. The 409s this can raise are about the
   * *meeting* — `agenda.py` freezes an agenda once the meeting starts — not about a
   * concurrent edit to the item, which does not exist yet.
   */
  async create(input: AgendaItemCreate): Promise<AgendaItem> {
    return apiPost<AgendaItem>("/agenda", input);
  },

  async update(id: string, patch: AgendaItemPatch): Promise<AgendaItem> {
    return apiPatch<AgendaItem>(`/agenda/${encodeURIComponent(id)}`, patch);
  },

  /** The server renumbers the items after the removed one, so callers re-list. */
  async remove(id: string, expectedVersion: number): Promise<void> {
    await apiDelete(`/agenda/${encodeURIComponent(id)}`, expectedVersion);
  },

  /**
   * Re-keys positions to match `orderedIds`, which must name every item of the
   * meeting exactly once. No `expected_version`: the full order is the guard, and
   * the server refuses a list that does not match the agenda it holds.
   */
  async reorder(meetingId: string, orderedIds: string[]): Promise<AgendaItem[]> {
    return apiPost<AgendaItem[]>("/agenda/reorder", {
      meeting_id: meetingId,
      ordered_item_ids: orderedIds,
    });
  },
};
