import { apiGet, apiGetOrNull } from "@/lib/http";

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

export const agendaApi = {
  /** A meeting's agenda, in the server's `position ASC` order. */
  async list(meetingId: string): Promise<AgendaItem[]> {
    return apiGet<AgendaItem[]>("/agenda", { meeting_id: meetingId });
  },

  async get(id: string): Promise<AgendaItem | null> {
    return apiGetOrNull<AgendaItem>(`/agenda/${encodeURIComponent(id)}`);
  },
};
