import type { BadgeTone } from "@/components/ui/badge";

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

export type AgendaItem = {
  id: string;
  title: string;
  order: number;
  timeboxMins: number;
  presenter?: string;
};

export type Meeting = {
  id: string;
  title: string;
  status: MeetingStatus;
  start: string; // ISO datetime
  end: string; // ISO datetime
  location?: string;
  objectives?: string;
  sensitivity: number; // 1..5 clearance ladder
  agenda: AgendaItem[];
};

// In-memory mock store, dated around the current demo month (July 2026).
const mockMeetings: Meeting[] = [
  {
    id: "m-14",
    title: "Board Meeting #14",
    status: "completed",
    start: "2026-07-09T10:00:00",
    end: "2026-07-09T11:30:00",
    location: "Zoom",
    objectives: "Q2 review, pricing model, hiring plan.",
    sensitivity: 2,
    agenda: [
      { id: "a1", title: "Q2 metrics review", order: 1, timeboxMins: 20, presenter: "Raj Malhotra" },
      { id: "a2", title: "Pricing model discussion", order: 2, timeboxMins: 25, presenter: "Priya Nair" },
      { id: "a3", title: "Hiring plan sign-off", order: 3, timeboxMins: 15 },
    ],
  },
  {
    id: "m-prod",
    title: "Product Review",
    status: "completed",
    start: "2026-07-15T11:00:00",
    end: "2026-07-15T12:00:00",
    location: "HQ — Room A",
    sensitivity: 1,
    agenda: [],
  },
  {
    id: "m-q3",
    title: "Q3 Board Meeting",
    status: "in_progress",
    start: "2026-07-21T09:00:00",
    end: "2026-07-21T11:00:00",
    location: "Zoom",
    objectives: "Q3 board pack, Series B terms, runway.",
    sensitivity: 3,
    agenda: [
      { id: "b1", title: "CEO update", order: 1, timeboxMins: 15, presenter: "Raj Malhotra" },
      { id: "b2", title: "Financials & runway", order: 2, timeboxMins: 20, presenter: "Priya Nair" },
      { id: "b3", title: "Series B terms", order: 3, timeboxMins: 30 },
    ],
  },
  {
    id: "m-comp",
    title: "Comp Committee Sync",
    status: "scheduled",
    start: "2026-07-21T14:00:00",
    end: "2026-07-21T15:00:00",
    location: "Google Meet",
    sensitivity: 4,
    agenda: [],
  },
  {
    id: "m-seq",
    title: "Investor Update — Sequoia",
    status: "scheduled",
    start: "2026-07-23T10:00:00",
    end: "2026-07-23T10:45:00",
    location: "Zoom",
    sensitivity: 3,
    agenda: [],
  },
  {
    id: "m-terms",
    title: "Series B Terms Review",
    status: "draft",
    start: "2026-07-28T16:00:00",
    end: "2026-07-28T17:00:00",
    sensitivity: 4,
    agenda: [],
  },
  {
    id: "m-aug",
    title: "Monthly Board Sync",
    status: "scheduled",
    start: "2026-08-04T10:00:00",
    end: "2026-08-04T11:00:00",
    location: "Zoom",
    sensitivity: 2,
    agenda: [],
  },
];

const clone = (m: Meeting): Meeting => structuredClone(m);
const delay = (ms = 400) => new Promise((r) => setTimeout(r, ms));

export type MeetingInput = Omit<Meeting, "id" | "agenda"> & { agenda?: AgendaItem[] };

/** Mocked Meridian meetings API. Simulates network latency; sorted by start time. */
export const meetingsApi = {
  async list(): Promise<Meeting[]> {
    await delay();
    return mockMeetings
      .slice()
      .sort((a, b) => a.start.localeCompare(b.start))
      .map(clone);
  },

  async get(id: string): Promise<Meeting | null> {
    await delay(200);
    const m = mockMeetings.find((x) => x.id === id);
    return m ? clone(m) : null;
  },

  async create(input: MeetingInput): Promise<Meeting> {
    await delay();
    const meeting: Meeting = { id: `m-${crypto.randomUUID().slice(0, 8)}`, agenda: [], ...input };
    mockMeetings.push(meeting);
    return clone(meeting);
  },

  async update(id: string, patch: Partial<MeetingInput>): Promise<Meeting> {
    await delay();
    const m = mockMeetings.find((x) => x.id === id);
    if (!m) throw new Error("Meeting not found");
    Object.assign(m, patch);
    return clone(m);
  },
};
