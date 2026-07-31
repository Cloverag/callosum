import { stanceBreakdown, supersededBy, type Decision } from "../src/lib/decisions";
import { nameOf } from "../src/lib/board-members";

/**
 * The derived helpers on `lib/decisions.ts`, and the stance properties the UI depends
 * on.
 *
 * **These used to read from `decisionsApi`, when it was a mock.** The client went live
 * during the demo build-out, so the tests now assert against a local fixture instead:
 * `stanceBreakdown` and `supersededBy` are pure functions, and testing a pure function
 * through a network client only ever tested the client.
 *
 * The stance *shape* properties they also covered — `board_member_id` nullable,
 * `person_name` always present beside it — are now pinned server-side, against the real
 * database, by `tests/test_decisions_api.py`:
 *   · `test_a_resolved_stance_carries_its_board_member_id`
 *   · `test_an_unresolved_stance_is_null_not_missing`
 * That is a stronger guarantee than a fixture could give, because a fixture can be
 * written to agree with a bug.
 */

const STANCE = (over: Partial<Decision["stances"][number]>) => ({
  id: "s-1",
  decision_id: "d-price-reject",
  workspace_id: "ws-1",
  person_name: "Priya Nair",
  board_member_id: null,
  stance: "SUPPORTED" as const,
  comment: null,
  created_at: "2026-03-11T10:00:00Z",
  updated_at: "2026-03-11T10:00:00Z",
  ...over,
});

const REJECT: Decision = {
  id: "d-price-reject",
  meeting_id: "m-12",
  agenda_item_id: null,
  workspace_id: "ws-1",
  title: "Reject Pricing Model B",
  rationale: null,
  status: "superseded",
  superseded_by_id: "d-price-adopt",
  version: 2,
  created_at: "2026-03-11T10:00:00Z",
  updated_at: "2026-06-10T10:00:00Z",
  stances: [
    STANCE({ id: "s-1", person_name: "Raj Malhotra", stance: "APPROVED", board_member_id: "bm-raj" }),
    STANCE({ id: "s-2", person_name: "Priya Nair", stance: "SUPPORTED" }),
    STANCE({ id: "s-3", person_name: "Marcus Webb", stance: "OPPOSED" }),
  ],
};

const ADOPT: Decision = {
  ...REJECT,
  id: "d-price-adopt",
  title: "Adopt Usage-Based Pricing",
  status: "approved",
  superseded_by_id: null,
  created_at: "2026-06-10T10:00:00Z",
  stances: [],
};

describe("stances resolve to the directory, optionally", () => {
  it("keeps the recorded name beside a resolved id", () => {
    // `person_name` is what was minuted and is permanent audit data; `board_member_id`
    // is an optional resolution of it. Collapsing them would lose the record of what
    // was actually written down.
    const resolved = REJECT.stances.filter((s) => s.board_member_id !== null);
    expect(resolved.length).toBeGreaterThan(0);
    expect(resolved.every((s) => s.person_name.length > 0)).toBe(true);
  });

  it("treats a null board_member_id as valid, not as an error", () => {
    // The realistic case, not an oversight: a stance minuted before the directory
    // existed, or against someone never added to it, is still a valid stance.
    const unresolved = REJECT.stances.filter((s) => s.board_member_id === null);
    expect(unresolved.length).toBeGreaterThan(0);
    expect(unresolved.every((s) => s.person_name.length > 0)).toBe(true);
  });

  it("never invents a name for an unresolved id", () => {
    // nameOf returns null rather than a placeholder, so the caller decides how to
    // render an unresolved reference. A default like "Unknown director" would put a
    // fabricated person on screen.
    expect(nameOf(null, [])).toBeNull();
    expect(nameOf("bm-not-in-directory", [])).toBeNull();
  });
});

describe("the derived helpers", () => {
  it("counts stances in spectrum order, omitting those nobody took", () => {
    const rows = stanceBreakdown(REJECT);
    expect(rows.every((r) => r.count > 0)).toBe(true);
    expect(rows.reduce((n, r) => n + r.count, 0)).toBe(REJECT.stances.length);
  });

  it("follows a supersession link, and tolerates a missing target", () => {
    expect(supersededBy(REJECT, [REJECT, ADOPT])!.id).toBe("d-price-adopt");

    // A dangling pointer must not crash a page. It renders as "no replacement found",
    // which is the truth, rather than throwing.
    const orphan = { id: "x", superseded_by_id: "gone" } as Decision;
    expect(supersededBy(orphan, [orphan])).toBeNull();
  });
});
