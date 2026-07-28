import { decisionsApi, stanceBreakdown, supersededBy, type Decision } from "../src/lib/decisions";
import { boardMembersApi, nameOf } from "../src/lib/board-members";

/**
 * `decision_stance.board_member_id` shipped in CP5a (`0012_board_member`) as a
 * composite `(board_member_id, workspace_id)` foreign key. `decisions.ts` had carried
 * a note saying it was still "coming in CP5" long after it arrived.
 *
 * The property worth pinning is not that the field exists — it is that it is
 * **nullable forever**, and that `person_name` survives beside it. Those two facts are
 * what stop a surface from treating an unresolved stance as an error, or from
 * replacing what was minuted with what the directory currently says.
 */

describe("stances resolve to the directory, optionally", () => {
  it("resolves a stance whose recorded name is in the directory", async () => {
    const [decisions, members] = await Promise.all([
      decisionsApi.list(),
      boardMembersApi.list({ include_inactive: true }),
    ]);
    const resolved = decisions
      .flatMap((d) => d.stances)
      .filter((s) => s.board_member_id !== null);

    expect(resolved.length).toBeGreaterThan(0);
    for (const s of resolved) {
      // A populated id must actually resolve. If it does not, the two mocks have
      // drifted apart and the real API would 404 on the same lookup.
      expect(nameOf(s.board_member_id, members)).not.toBeNull();
    }
  });

  it("keeps the recorded name even when the stance resolves", async () => {
    // person_name is what was minuted and is permanent audit data; board_member_id is
    // an optional resolution of it. Collapsing them would lose the record of what was
    // actually written down.
    const decisions = await decisionsApi.list();
    for (const s of decisions.flatMap((d) => d.stances)) {
      expect(typeof s.person_name).toBe("string");
      expect(s.person_name.length).toBeGreaterThan(0);
    }
  });

  it("leaves board_member_id null for a name the directory does not know", async () => {
    // The realistic case, not an oversight: a stance minuted before the directory
    // existed, or against someone never added to it, is still a valid stance. A mock
    // where every row resolved would let an unresolved-stance bug go unnoticed.
    const decisions = await decisionsApi.list();
    const unresolved = decisions
      .flatMap((d) => d.stances)
      .filter((s) => s.board_member_id === null);

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

describe("existing decision contract still holds", () => {
  it("counts stances in spectrum order, omitting those nobody took", async () => {
    const d = (await decisionsApi.get("d-price-reject"))!;
    const rows = stanceBreakdown(d);
    expect(rows.every((r) => r.count > 0)).toBe(true);
    expect(rows.reduce((n, r) => n + r.count, 0)).toBe(d.stances.length);
  });

  it("follows a supersession link, and tolerates a missing target", async () => {
    const all = await decisionsApi.list();
    const superseded = all.find((d) => d.id === "d-price-reject")!;
    expect(supersededBy(superseded, all)!.id).toBe("d-price-adopt");

    const orphan = { id: "x", superseded_by_id: "gone" } as Decision;
    expect(supersededBy(orphan, [orphan])).toBeNull();
  });
});
