import type { BadgeTone } from "@/components/ui/badge";
import { apiGet, apiGetOrNull, apiPatch, apiPost } from "@/lib/http";

/**
 * `meridian/meetings.py:31-35`. **These are the only five states the domain has.**
 *
 * This type previously declared `review` and `archived` — taken from the PRD's prose
 * lifecycle — and omitted `cancelled`, which the domain does have. Neither phantom
 * status was reachable: `transition_status` would reject both, so a meeting could
 * never arrive in one, and the labels and tones for them were styling for a state
 * that could not occur.
 *
 * The missing `cancelled` was the sharper half. Board packs lock on
 * `{in_progress, completed, cancelled}` and minutes on `{draft, scheduled, cancelled}`;
 * anything deriving a lock rule from this type would have omitted it and concluded a
 * cancelled meeting's pack was still editable. `packs.ts` and `minutes.ts` avoided
 * that by declaring their own lock sets against the backend rather than binding to
 * this type — a workaround that is no longer needed, though their tests still pin the
 * values independently, which is the safer place for that assertion to live.
 *
 * Closes #47.
 */
export type MeetingStatus =
  | "draft"
  | "scheduled"
  | "in_progress"
  | "completed"
  | "cancelled";

export const MEETING_STATUS_LABEL: Record<MeetingStatus, string> = {
  draft: "Draft",
  scheduled: "Scheduled",
  in_progress: "In progress",
  completed: "Completed",
  cancelled: "Cancelled",
};

export const MEETING_STATUS_TONE: Record<MeetingStatus, BadgeTone> = {
  draft: "neutral",
  scheduled: "info",
  in_progress: "warning",
  completed: "success",
  // Neutral rather than danger: a cancelled meeting is a closed record, not a
  // failure, and colouring it as an error would misreport a routine outcome.
  cancelled: "neutral",
};

// Tailwind bg-* token classes for the small status dot in calendar cells.
export const MEETING_STATUS_DOT: Record<MeetingStatus, string> = {
  draft: "bg-muted-foreground",
  scheduled: "bg-info",
  in_progress: "bg-warning",
  completed: "bg-success",
  cancelled: "bg-subtle-foreground",
};

export const MEETING_STATUSES = Object.keys(MEETING_STATUS_LABEL) as MeetingStatus[];

/**
 * Mirrors `meridian/meetings.py`. **Three fields the mock carried are gone**, because
 * the domain has never had them: `objectives`, `sensitivity`, and `agenda`.
 *
 * `agenda` was the consequential one — agenda items are their own aggregate (CP2),
 * and embedding them here let two surfaces render an agenda with nothing to fetch it
 * from. They now use `lib/agenda.ts`.
 *
 * `sensitivity` is not merely missing, it is wrong in principle: clearance is a
 * property of a membership, not of a meeting. A "Clearance Level N" stat on a meeting
 * asserted something this system does not model.
 */
export type Meeting = {
  id: string;
  title: string;
  status: MeetingStatus;
  /**
   * ISO, or **null** — a `draft` meeting has no window until it is scheduled.
   * The mock declared these as required `start`/`end`; the domain calls them
   * `scheduled_start`/`scheduled_end` and allows both to be absent, so anything
   * doing `new Date(m.start)` on a draft was building an Invalid Date.
   */
  scheduled_start: string | null;
  scheduled_end: string | null;
  location: string | null;
  workspace_id: string;
  /** Optimistic-concurrency counter. */
  version: number;
  created_by: string | null;
  created_at: string; // ISO
  updated_at: string; // ISO
};

// In-memory mock store, dated around the current demo month (July 2026).

// --- Derived helpers -------------------------------------------------------

/** A meeting with a concrete window — the only kind a calendar can place. */
export type ScheduledMeeting = Meeting & {
  scheduled_start: string;
  scheduled_end: string;
};

/**
 * Narrows to meetings that have a window.
 *
 * A `draft` has none, and the calendar cannot render a date it does not have. This is
 * a type guard rather than a filter helper so the compiler stops anyone reading
 * `scheduled_start` without asking first — which is exactly what the old required
 * `start` field let them do.
 */
export function isScheduled(m: Meeting): m is ScheduledMeeting {
  return m.scheduled_start !== null && m.scheduled_end !== null;
}

/** Only the meetings a calendar can place, in the server's order. */
export function scheduledOnly(meetings: Meeting[]): ScheduledMeeting[] {
  return meetings.filter(isScheduled);
}

// --- API client ------------------------------------------------------------

/**
 * Meridian meetings API. Live as of CP-C; the in-memory mock is gone.
 *
 * `list` returns undated drafts too. Hiding them here would make the meetings list
 * disagree with the database to suit the calendar — the calendar narrows with
 * `scheduledOnly()` instead, at the point where the constraint actually applies.
 */
export const meetingsApi = {
  async list(opts?: { status?: MeetingStatus }): Promise<Meeting[]> {
    return apiGet<Meeting[]>("/meetings", { status: opts?.status });
  },

  async get(id: string): Promise<Meeting | null> {
    return apiGetOrNull<Meeting>(`/meetings/${encodeURIComponent(id)}`);
  },

  /**
   * Creates a `draft`. The API sets `created_by` from the session — there is no
   * parameter for it here because there is no parameter for it there (ADR-013).
   */
  async create(input: MeetingCreate): Promise<Meeting> {
    return apiPost<Meeting>("/meetings", input);
  },

  /**
   * Updates only the fields present in `changes`.
   *
   * **Send what changed, not the whole form.** The API distinguishes an omitted field
   * from an explicit `null`: omitted leaves the value alone, `null` clears it. Passing
   * a form's entire state would send `null` for every empty input and wipe fields the
   * user never touched. `changesBetween()` below exists so no surface has to remember.
   */
  async update(id: string, expectedVersion: number, changes: MeetingChanges): Promise<Meeting> {
    return apiPatch<Meeting>(`/meetings/${encodeURIComponent(id)}`, {
      expected_version: expectedVersion,
      ...changes,
    });
  },

  /** Moves a meeting through its lifecycle. An illegal move is a 409, not a 422. */
  async transition(id: string, newStatus: MeetingStatus, expectedVersion: number): Promise<Meeting> {
    return apiPost<Meeting>(`/meetings/${encodeURIComponent(id)}/transition`, {
      new_status: newStatus,
      expected_version: expectedVersion,
    });
  },
};

/** The fields `POST /api/meetings` accepts. `status` and `created_by` are not among them. */
export type MeetingCreate = {
  title: string;
  scheduled_start?: string | null;
  scheduled_end?: string | null;
  location?: string | null;
};

/** The patchable fields. Absent means "leave alone"; `null` means "clear". */
export type MeetingChanges = {
  title?: string;
  scheduled_start?: string | null;
  scheduled_end?: string | null;
  location?: string | null;
};

/**
 * The minimal patch that turns `before` into `after`.
 *
 * Exists because the tri-state is easy to get wrong in exactly one direction: a
 * surface that sends its whole form state clears every field the user left empty. This
 * compares field by field and emits only what actually differs, so an untouched
 * `location` is absent from the request rather than present as `null`.
 *
 * `title` is never emitted as `null` — it is `NOT NULL` in the schema, so an empty
 * title is a validation error for the form to catch, not a clear instruction.
 */
export function changesBetween(before: Meeting, after: MeetingChanges): MeetingChanges {
  const changes: MeetingChanges = {};
  if (after.title !== undefined && after.title !== before.title) changes.title = after.title;
  if (after.scheduled_start !== undefined && after.scheduled_start !== before.scheduled_start) {
    changes.scheduled_start = after.scheduled_start;
  }
  if (after.scheduled_end !== undefined && after.scheduled_end !== before.scheduled_end) {
    changes.scheduled_end = after.scheduled_end;
  }
  if (after.location !== undefined && after.location !== before.location) {
    changes.location = after.location;
  }
  return changes;
}
