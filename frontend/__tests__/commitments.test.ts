import {
  COMMITMENT_TRANSITIONS,
  OPEN_STATUSES,
  isOpen,
  isOverdue,
  isTerminal,
  latestUpdate,
  todayLocal,
  type Commitment,
} from "../src/lib/commitments";


/**
 * Two properties of this contract are easy to get wrong, and both are tested hardest:
 *
 * 1. `blocked` is NOT terminal. Blocked work is expected to resume; a surface that
 *    files it with the cancelled work misreports recoverable commitments as dead.
 * 2. Closed work is never overdue. It may have been delivered late, but an overdue
 *    list that includes finished work is not an overdue list.
 *
 * Delivery is inert in P2 — no adapter exists — so every row must be
 * `not_dispatched`. A mock inventing `delivered` rows would be fiction about a
 * feature the product does not have.
 */


/**
 * A local fixture, because `commitmentsApi` went live during the demo build-out.
 *
 * The helpers below — `isOverdue`, `isOpen`, `isTerminal`, `latestUpdate` — are pure
 * functions, and testing a pure function through a network client only ever tests the
 * client. The *data* properties these once asserted against the mock (delivery inert,
 * an update trail that never carries a status change without a note) are pinned
 * server-side against the real database in `tests/test_d2c_write_api.py`:
 *   · `test_an_update_requires_a_note_even_without_a_status_change`
 *   · `test_there_is_no_delivery_endpoint`
 *   · `test_blocked_is_not_terminal`
 */
const COMMITMENT = (over: Partial<Commitment> = {}): Commitment => ({
  id: "cmt-1",
  decision_id: "d-1",
  resolution_id: null,
  owner_board_member_id: "bm-priya",
  accountable_team: "Finance",
  title: "Bring the revised FY27 forecast",
  detail: null,
  due_date: "2026-09-30",
  status: "open",
  completed_at: null,
  external_system: null,
  external_task_id: null,
  delivery_status: "not_dispatched",
  delivery_attempts: 0,
  version: 1,
  created_at: "2026-06-10T10:00:00Z",
  updated_at: "2026-06-10T10:00:00Z",
  workspace_id: "ws-1",
  updates: [],
  ...over,
});

describe("the status machine mirrors meridian/commitments.py", () => {
  it("does not let open jump straight to completed", () => {
    // That would skip the work. open -> in_progress -> completed is the path.
    expect(COMMITMENT_TRANSITIONS.open).not.toContain("completed");
    expect(COMMITMENT_TRANSITIONS.in_progress).toContain("completed");
  });

  it("treats blocked as recoverable, not terminal", () => {
    expect(isTerminal("blocked")).toBe(false);
    expect(COMMITMENT_TRANSITIONS.blocked).toContain("in_progress");
  });

  it("treats only completed and cancelled as terminal", () => {
    expect(isTerminal("completed")).toBe(true);
    expect(isTerminal("cancelled")).toBe(true);
    for (const s of ["open", "in_progress", "blocked"] as const) {
      expect(isTerminal(s)).toBe(false);
    }
  });

  it("counts blocked work as still outstanding", () => {
    expect(OPEN_STATUSES).toEqual(["open", "in_progress", "blocked"]);
  });
});

describe("overdue", () => {
  const base = {
    status: "open",
    due_date: "2026-07-25",
  } as Commitment;

  it("is true only once the due date has passed", () => {
    expect(isOverdue(base, "2026-07-26")).toBe(true);
    expect(isOverdue(base, "2026-07-25")).toBe(false); // due today is not late
    expect(isOverdue(base, "2026-07-24")).toBe(false);
  });

  it("is false for closed work, however late it was", () => {
    // A completed commitment cannot be overdue, whatever its date says.
    const c = COMMITMENT({ status: "completed", due_date: "2020-01-01" });
    expect(isOverdue(c, "2026-08-01")).toBe(false);
  });

  it("is false for undated work", () => {
    expect(isOverdue({ ...base, due_date: null } as Commitment, "2099-01-01")).toBe(false);
  });

  it("is true for blocked work past its date", () => {
    // Blocked is not terminal, so blocked work still runs late.
    const c = COMMITMENT({ status: "blocked", due_date: "2026-01-01" });
    expect(isOverdue(c, "2026-08-01")).toBe(true);
  });

  it("compares calendar days without a timezone shift", () => {
    // Both sides are YYYY-MM-DD, so this is a string compare by design. Parsing a
    // bare date into a Date would make it UTC midnight and shift the day west of
    // Greenwich — the same bug `dayKey` in lib/calendar.ts exists to avoid.
    expect(isOverdue({ ...base, due_date: "2026-12-31" } as Commitment, "2027-01-01")).toBe(true);
    expect(isOverdue({ ...base, due_date: "2027-01-01" } as Commitment, "2026-12-31")).toBe(false);
  });

  it("todayLocal formats the local calendar day, zero-padded", () => {
    expect(todayLocal(new Date(2026, 6, 9))).toBe("2026-07-09");
    expect(todayLocal(new Date(2026, 11, 25))).toBe("2026-12-25");
    // Late evening local is still today, not tomorrow-in-UTC.
    expect(todayLocal(new Date(2026, 6, 9, 23, 30))).toBe("2026-07-09");
  });
});

describe("delivery is inert until P8", () => {
  it("models delivery state without ever claiming a dispatch", () => {
    // Modelled and returned, doing nothing until P8 — serialised as stored rather
    // than hidden, because a field reading `not_dispatched` is honest and a silently
    // withheld one is not. That nothing drives it is asserted server-side by
    // `test_there_is_no_delivery_endpoint`.
    const c = COMMITMENT();
    expect(c.delivery_status).toBe("not_dispatched");
    expect(c.delivery_attempts).toBe(0);
    expect(c.external_system).toBeNull();
    expect(c.external_task_id).toBeNull();
  });
});

describe("the update trail", () => {
  it("returns the most recent update, or null when there are none", () => {
    expect(latestUpdate(COMMITMENT())).toBeNull();

    const withTrail = COMMITMENT({
      updates: [
        { id: "u1", commitment_id: "cmt-1", note: "Started", new_status: "in_progress",
          author_board_member_id: null, created_at: "2026-06-11T09:00:00Z", workspace_id: "ws-1" },
        { id: "u2", commitment_id: "cmt-1", note: "Draft circulated", new_status: null,
          author_board_member_id: null, created_at: "2026-06-20T09:00:00Z", workspace_id: "ws-1" },
      ],
    });
    // An update with `new_status: null` is a progress note that changed nothing —
    // valid, and still required to carry a note. Enforced server-side by
    // `test_an_update_requires_a_note_even_without_a_status_change`.
    expect(latestUpdate(withTrail)!.id).toBe("u2");
    expect(withTrail.updates.every((u) => u.note.length > 0)).toBe(true);
  });
});

