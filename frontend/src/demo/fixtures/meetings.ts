import type { Meeting } from "@/lib/meetings";
import type { AgendaItem } from "@/lib/agenda";
import { AGENDA, DEMO_WORKSPACE_ID, MEETING } from "./ids";

/**
 * Five meetings, chosen to cover the status machine rather than to look busy.
 *
 * `MEETING_STATUSES` has five values and every one of them appears exactly once
 * — including `cancelled`, which surfaces render with different affordances
 * (no pack editing, no minutes) that a dataset of three scheduled meetings
 * would never exercise. `PACK_LOCKED_MEETING_STATUSES` and
 * `MINUTES_LOCKED_MEETING_STATUSES` are also both non-trivially hit.
 *
 * The draft meeting has null start and end. That is the case `isScheduled`
 * exists for and the one the calendar has to drop rather than render at the
 * epoch.
 *
 * Dates sit either side of 2026-09-02 so "upcoming" and "past" are both
 * populated. They are fixed strings, not offsets from `Date.now()`: a fixture
 * that moves with the clock makes a screenshot unreproducible and makes a test
 * that asserts against it fail on a date nobody chose.
 */
export const MEETINGS: Meeting[] = [
  {
    id: MEETING[0], title: "Q2 Board Meeting", status: "completed",
    scheduled_start: "2026-07-15T13:00:00Z", scheduled_end: "2026-07-15T15:30:00Z",
    location: "Bridgewater House, London", workspace_id: DEMO_WORKSPACE_ID,
    version: 8, created_by: null,
    created_at: "2026-06-10T09:00:00Z", updated_at: "2026-07-15T15:31:00Z",
    importance: "routine",
  },
  {
    id: MEETING[1], title: "Series B Term Sheet Review", status: "completed",
    scheduled_start: "2026-08-05T16:00:00Z", scheduled_end: "2026-08-05T17:00:00Z",
    location: "Video conference", workspace_id: DEMO_WORKSPACE_ID,
    version: 6, created_by: null,
    created_at: "2026-07-28T11:20:00Z", updated_at: "2026-08-05T17:02:00Z",
    importance: "critical",
  },
  {
    id: MEETING[2], title: "September Board Meeting", status: "scheduled",
    scheduled_start: "2026-09-09T13:00:00Z", scheduled_end: "2026-09-09T16:00:00Z",
    location: "Bridgewater House, London", workspace_id: DEMO_WORKSPACE_ID,
    version: 3, created_by: null,
    created_at: "2026-08-01T09:00:00Z", updated_at: "2026-08-28T09:15:00Z",
    importance: "routine",
  },
  {
    id: MEETING[3], title: "Audit & Risk Committee", status: "in_progress",
    scheduled_start: "2026-09-02T09:00:00Z", scheduled_end: "2026-09-02T10:30:00Z",
    location: "Video conference", workspace_id: DEMO_WORKSPACE_ID,
    version: 2, created_by: null,
    created_at: "2026-08-18T14:00:00Z", updated_at: "2026-09-02T09:01:00Z",
    importance: "routine",
  },
  {
    id: MEETING[4], title: "Compensation Review (unscheduled)", status: "draft",
    scheduled_start: null, scheduled_end: null,
    location: null, workspace_id: DEMO_WORKSPACE_ID,
    version: 1, created_by: null,
    created_at: "2026-08-30T16:45:00Z", updated_at: "2026-08-30T16:45:00Z",
    importance: "routine",
  },
  {
    // Sixth and last, so that every one of the five `MeetingStatus` values is
    // represented exactly once across this list.
    id: MEETING[5], title: "Emergency Liquidity Call", status: "cancelled",
    scheduled_start: "2026-08-21T18:00:00Z", scheduled_end: "2026-08-21T18:45:00Z",
    location: "Video conference", workspace_id: DEMO_WORKSPACE_ID,
    version: 2, created_by: null,
    created_at: "2026-08-20T22:10:00Z", updated_at: "2026-08-21T08:00:00Z",
    importance: "critical",
  },
];

const item = (
  n: number, meeting: string, position: number, title: string,
  description: string | null, duration: number | null, presenter: string | null,
): AgendaItem => ({
  id: AGENDA[n], meeting_id: meeting, workspace_id: DEMO_WORKSPACE_ID,
  title, description, duration_minutes: duration, presenter, position,
  version: 1, created_at: "2026-08-01T09:00:00Z", updated_at: "2026-08-01T09:00:00Z",
});

/**
 * Agenda items for the three meetings that have one.
 *
 * The draft and cancelled meetings deliberately have none — an empty agenda is a
 * state `/prepare` and the meeting detail both render, and a fixture set where
 * every meeting is fully populated never shows it.
 */
export const AGENDA_ITEMS: AgendaItem[] = [
  item(0, MEETING[2], 1, "Apologies and conflicts of interest", null, 5, "Grace Chen"),
  item(1, MEETING[2], 2, "Minutes of the Q2 meeting", "For approval.", 10, "Grace Chen"),
  item(2, MEETING[2], 3, "CEO report", "Trading, hiring, runway.", 30, "Daniel Reyes"),
  item(3, MEETING[2], 4, "Series B closing conditions", "Remaining CPs and the timetable.", 45, "Amara Okonkwo"),
  item(4, MEETING[2], 5, "Any other business", null, null, null),
  item(5, MEETING[0], 1, "CEO report", null, 30, "Daniel Reyes"),
  item(6, MEETING[0], 2, "FY27 budget approval", "Board approval sought.", 40, "Daniel Reyes"),
  item(7, MEETING[3], 1, "External audit findings", "Two management-letter points.", 40, "Grace Chen"),
  item(8, MEETING[3], 2, "Risk register review", null, 30, "Amara Okonkwo"),
];
