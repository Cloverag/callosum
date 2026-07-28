import {
  RESOLUTION_TRANSITIONS,
  COUNTED_VOTES,
  isTerminal,
  outcomeDivergesFromTally,
  resolutionsApi,
  supersededBy,
  tally,
  type Resolution,
} from "../src/lib/resolutions";
import { boardMembersApi, initialsOf, nameOf } from "../src/lib/board-members";

/**
 * The resolutions surface has one job it can get catastrophically wrong: presenting
 * the vote tally as the outcome.
 *
 * `carried` is a simple majority of votes cast and is advisory. Quorum and
 * supermajority rules vary per board and are not recorded in this system, so a
 * surface that derived the result from arithmetic would be asserting governance
 * nobody configured. The backend has a test that adopts a motion the tally says did
 * not carry; these are the frontend half of that guarantee.
 */

describe("tally", () => {
  it("counts every vote type", async () => {
    const r = (await resolutionsApi.get("res-seriesb"))!;
    const t = tally(r);
    expect([t.for, t.against, t.abstain, t.recused]).toEqual([3, 0, 0, 1]);
  });

  it("excludes abstentions and recusals from the counted total", async () => {
    // An abstention is a deliberate non-vote; a recusal is a declared conflict.
    // Counting either as opposition would misreport the board.
    const r = (await resolutionsApi.get("res-seriesb"))!;
    const t = tally(r);
    expect(t.counted).toBe(3);
    expect(t.counted).toBe(t.for + t.against);
    expect(COUNTED_VOTES).toEqual(["for", "against"]);
  });

  it("does not carry on a tie", () => {
    const r = {
      votes: [
        { vote: "for" }, { vote: "against" },
      ],
    } as Resolution;
    expect(tally(r).carried).toBe(false);
  });

  it("returns zeroes for an unvoted resolution", async () => {
    const r = (await resolutionsApi.get("res-pricing-v2"))!;
    expect(r.votes).toEqual([]);
    const t = tally(r);
    expect([t.for, t.against, t.counted, t.carried]).toEqual([0, 0, 0, false]);
  });
});

describe("the tally is advisory, never the outcome", () => {
  it("detects an adopted resolution the arithmetic says did not carry", async () => {
    // res-hiring: 1 for, 1 against, 1 recused — adopted anyway on the chair's
    // casting vote. This is legitimate, and the surface must be able to say so.
    const r = (await resolutionsApi.get("res-hiring"))!;
    expect(r.status).toBe("adopted");
    expect(tally(r).carried).toBe(false);
    expect(outcomeDivergesFromTally(r)).toBe(true);
  });

  it("does not flag a resolution whose outcome matches the arithmetic", async () => {
    const r = (await resolutionsApi.get("res-seriesb"))!;
    expect(r.status).toBe("adopted");
    expect(tally(r).carried).toBe(true);
    expect(outcomeDivergesFromTally(r)).toBe(false);
  });

  it("does not flag a rejection the arithmetic agrees with", async () => {
    const r = (await resolutionsApi.get("res-berlin"))!;
    expect(r.status).toBe("rejected");
    expect(outcomeDivergesFromTally(r)).toBe(false);
  });

  it("never flags a draft or superseded resolution", async () => {
    // Divergence is only meaningful against a recorded outcome. A draft has none.
    for (const id of ["res-pricing-v2", "res-pricing-v1"]) {
      const r = (await resolutionsApi.get(id))!;
      expect(outcomeDivergesFromTally(r)).toBe(false);
    }
  });

  it("does not flag an outcome recorded with no counted votes", () => {
    // All-abstain or all-recused. There is no arithmetic to disagree with, so
    // claiming divergence would be inventing a contradiction.
    const r = {
      status: "adopted",
      votes: [{ vote: "abstain" }, { vote: "recused" }],
    } as Resolution;
    expect(outcomeDivergesFromTally(r)).toBe(false);
  });
});

describe("status machine mirrors meridian/resolutions.py", () => {
  it("allows only draft to move", () => {
    expect(RESOLUTION_TRANSITIONS.draft).toEqual(["adopted", "rejected"]);
  });

  it("treats adopted, rejected and superseded as terminal", () => {
    // adopted is terminal because its only exit is supersede_resolution(), which
    // creates a NEW record — that is what keeps an adopted resolution immutable.
    for (const s of ["adopted", "rejected", "superseded"] as const) {
      expect(isTerminal(s)).toBe(true);
    }
    expect(isTerminal("draft")).toBe(false);
  });

  it("has no archived status", async () => {
    // #23 asked whether `archived` earns its place. It does not: superseded_by_id
    // already identifies a superseded resolution.
    expect(Object.keys(RESOLUTION_TRANSITIONS)).not.toContain("archived");
  });
});

describe("supersession", () => {
  it("links a superseded version to its amendment", async () => {
    const all = await resolutionsApi.list();
    const v1 = all.find((r) => r.id === "res-pricing-v1")!;
    expect(supersededBy(v1, all)!.id).toBe("res-pricing-v2");
  });

  it("returns null when the replacement is not in the caller's set", () => {
    const orphan = { id: "r1", superseded_by_id: "r2-invisible" } as Resolution;
    expect(supersededBy(orphan, [orphan])).toBeNull();
  });

  it("starts the new version unvoted", async () => {
    // Votes were cast on the old wording. Carrying them forward would attribute to
    // a director a vote on text they never saw.
    const v2 = (await resolutionsApi.get("res-pricing-v2"))!;
    expect(v2.version_no).toBe(2);
    expect(v2.votes).toEqual([]);
  });
});

describe("legal scope", () => {
  it("pins signing_state to not_applicable on every resolution", async () => {
    // E-signature, legal validity and jurisdiction are P8. Nothing on this surface
    // may imply a resolution has been signed or is binding.
    const all = await resolutionsApi.list();
    expect(all.length).toBeGreaterThan(0);
    for (const r of all) expect(r.signing_state).toBe("not_applicable");
  });
});

describe("list contract", () => {
  it("orders by version_no DESC then created_at DESC, mirroring list_resolutions", async () => {
    const forDecision = await resolutionsApi.list({ decision_id: "d-price-adopt" });
    expect(forDecision.map((r) => r.id)).toEqual(["res-pricing-v2", "res-pricing-v1"]);
  });

  it("filters by decision and by status", async () => {
    const adopted = await resolutionsApi.list({ status: "adopted" });
    expect(adopted.every((r) => r.status === "adopted")).toBe(true);
    expect(adopted.length).toBeGreaterThan(0);
  });

  it("returns null for a resolution that does not exist", async () => {
    expect(await resolutionsApi.get("res-nope")).toBeNull();
  });
});

describe("voters resolve through the board directory", () => {
  it("resolves every seeded vote to a real member", async () => {
    // board_member_id is a real foreign key as of CP5a, unlike
    // decision_stance.person_name which is free text. If a seeded vote cannot be
    // resolved, the two mocks have drifted apart.
    const members = await boardMembersApi.list({ include_inactive: true });
    const all = await resolutionsApi.list();
    for (const r of all) {
      for (const v of r.votes) {
        expect(nameOf(v.board_member_id, members)).not.toBeNull();
      }
    }
  });

  it("returns null for an unresolvable id rather than inventing a name", () => {
    // The directory is clearance-scoped, so a voter the reader cannot resolve is a
    // legitimate state. A placeholder name would be a fabricated person.
    expect(nameOf("bm-nobody", [])).toBeNull();
    expect(nameOf(null, [])).toBeNull();
  });

  it("includes inactive members, because they still cast historic votes", async () => {
    const active = await boardMembersApi.list();
    const withInactive = await boardMembersApi.list({ include_inactive: true });
    expect(withInactive.length).toBeGreaterThan(active.length);
    expect(active.every((m) => m.active)).toBe(true);
  });

  it("derives initials from the first and last word", () => {
    expect(initialsOf("Priya Nair")).toBe("PN");
    expect(initialsOf("Raj")).toBe("R");
    expect(initialsOf("  Tobi   Adeyemi  ")).toBe("TA");
  });
});

describe("board directory contract", () => {
  it("carries no clearance field", async () => {
    // Clearance belongs to `membership`. Two sources of truth for clearance is how
    // RBAC gets bypassed, and board_member deliberately has no such column.
    const members = await boardMembersApi.list();
    for (const key of ["clearance", "sensitivity"]) {
      expect(Object.keys(members[0])).not.toContain(key);
    }
  });

  it("allows a member with no login", async () => {
    // A non-executive director who never signs in is still recordable and votable.
    const members = await boardMembersApi.list();
    expect(members.some((m) => m.principal_id === null)).toBe(true);
  });
});
