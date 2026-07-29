import {
  COMMITMENT_TRANSITIONS,
  OPEN_STATUSES,
  commitmentsApi,
  isOpen,
  isOverdue,
  isTerminal,
  latestUpdate,
  todayLocal,
  type Commitment,
} from "../src/lib/commitments";
import { nameOf } from "../src/lib/board-members";
// The directory is a live API client as of CP-C. These tests only need a member
// list to resolve ids against — that is a cross-module contract assertion, not a
// client test — so they read the fixture directly rather than stubbing fetch.
import { BOARD_MEMBER_FIXTURES } from "../test-support/board-members-fixture";

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

  it("is false for closed work, however late it was", async () => {
    // cmt-forecast-revision was due 24 July and completed on the 28th. Late in the
    // record, but not outstanding — so it must not appear on an overdue list.
    const c = (await commitmentsApi.get("cmt-forecast-revision"))!;
    expect(c.status).toBe("completed");
    expect(c.due_date! < c.completed_at!.slice(0, 10)).toBe(true);
    expect(isOverdue(c, "2026-12-31")).toBe(false);
  });

  it("is false for undated work", () => {
    expect(isOverdue({ ...base, due_date: null } as Commitment, "2099-01-01")).toBe(false);
  });

  it("is true for blocked work past its date", async () => {
    // Blocked is still outstanding. Work stuck behind a blocker is exactly what a
    // board most wants surfaced, so excluding it would defeat the point.
    const c = (await commitmentsApi.get("cmt-preference-model"))!;
    expect(c.status).toBe("blocked");
    expect(isOverdue(c, "2026-07-26")).toBe(true);
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
  it("every commitment is not_dispatched", async () => {
    // No adapter exists, so this is the only state the backend can produce. A mock
    // with `delivered` rows would be fiction about a feature that does not exist.
    const all = await commitmentsApi.list();
    expect(all.length).toBeGreaterThan(0);
    for (const c of all) {
      expect(c.delivery_status).toBe("not_dispatched");
      expect(c.delivery_attempts).toBe(0);
      expect(c.external_task_id).toBeNull();
      expect(c.external_system).toBeNull();
    }
  });

  it("never claims delivery without an external reference", async () => {
    // FR-EXEC-03 as a CHECK constraint in 0015: `delivered` requires both an
    // external system and task id. The mock must not be able to violate what the
    // database forbids.
    const all = await commitmentsApi.list();
    for (const c of all) {
      if (c.delivery_status === "delivered") {
        expect(c.external_system).not.toBeNull();
        expect(c.external_task_id).not.toBeNull();
      }
    }
  });
});

describe("the update trail", () => {
  it("is ordered oldest first and records the transitions", async () => {
    const c = (await commitmentsApi.get("cmt-forecast-revision"))!;
    expect(c.updates.map((u) => u.new_status)).toEqual(["in_progress", "completed"]);
    const stamps = c.updates.map((u) => u.created_at);
    expect([...stamps].sort()).toEqual(stamps);
  });

  it("allows progress notes that change nothing", async () => {
    const c = (await commitmentsApi.get("cmt-migration-plan"))!;
    expect(c.updates.some((u) => u.new_status === null)).toBe(true);
  });

  it("never carries a status change without a note", async () => {
    // The backend requires a note on every update, which is what makes the trail a
    // record rather than a status field.
    const all = await commitmentsApi.list();
    for (const c of all) {
      for (const u of c.updates) {
        expect(u.note.trim().length).toBeGreaterThan(0);
      }
    }
  });

  it("latestUpdate returns the newest, or null for an untouched commitment", async () => {
    const withTrail = (await commitmentsApi.get("cmt-preference-model"))!;
    expect(latestUpdate(withTrail)!.new_status).toBe("blocked");

    const untouched = (await commitmentsApi.get("cmt-hiring-reqs"))!;
    expect(untouched.updates).toEqual([]);
    expect(latestUpdate(untouched)).toBeNull();
  });
});

describe("list contract", () => {
  it("orders by due date with undated work last", async () => {
    const all = await commitmentsApi.list();
    const dated = all.filter((c) => c.due_date);
    const undated = all.filter((c) => !c.due_date);

    // Undated work is not the most urgent thing on the list.
    expect(all.slice(0, dated.length).every((c) => c.due_date)).toBe(true);
    expect(undated.length).toBeGreaterThan(0);

    const dates = dated.map((c) => c.due_date!);
    expect([...dates].sort()).toEqual(dates);
  });

  it("open_only selects outstanding work across three statuses", async () => {
    const open = await commitmentsApi.list({ open_only: true });
    expect(open.every(isOpen)).toBe(true);
    // The question a board asks that no single status answers.
    expect(new Set(open.map((c) => c.status)).size).toBeGreaterThan(1);
  });

  it("filters by decision, owner and status", async () => {
    expect((await commitmentsApi.list({ status: "blocked" })).every((c) => c.status === "blocked")).toBe(true);
    expect((await commitmentsApi.list({ owner_board_member_id: "bm-priya" })).every((c) => c.owner_board_member_id === "bm-priya")).toBe(true);
    expect((await commitmentsApi.list({ decision_id: "d-hire" })).every((c) => c.decision_id === "d-hire")).toBe(true);
  });

  it("returns null for a commitment that does not exist", async () => {
    expect(await commitmentsApi.get("cmt-nope")).toBeNull();
  });
});

describe("provenance", () => {
  it("every commitment names a source decision", async () => {
    // NOT NULL in the schema — untraceable work is what this product prevents.
    const all = await commitmentsApi.list();
    for (const c of all) {
      expect(c.decision_id).toBeTruthy();
    }
  });

  it("resolves every owner through the board directory", async () => {
    const all = await commitmentsApi.list();
    const members = BOARD_MEMBER_FIXTURES;
    for (const c of all) {
      expect(nameOf(c.owner_board_member_id, members)).not.toBeNull();
    }
  });

  it("leaves resolution_id null where the decision produced no instrument", async () => {
    // Not every decision is formalised as a resolution, so this must be nullable in
    // practice and not merely in the type.
    const all = await commitmentsApi.list();
    expect(all.some((c) => c.resolution_id === null)).toBe(true);
    expect(all.some((c) => c.resolution_id !== null)).toBe(true);
  });
});
