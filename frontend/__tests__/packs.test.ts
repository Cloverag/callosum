import {
  PACK_LOCKED_MEETING_STATUSES,
  isEditable,
  packsApi,
  resolveItems,
  supersededBy,
  type BoardPack,
} from "../src/lib/packs";
import {
  INTERNAL_CLEARANCE,
  INVESTOR_CLEARANCE,
  RESTRICTED_CLEARANCE,
  documentsApi,
} from "../src/lib/documents";

/**
 * These tests exist to protect one property: a reader must not be able to work
 * out that anything was withheld from a board pack.
 *
 * That is a stronger guarantee than "restricted content is not shown". Content
 * can be absent and still leak — through a gap in the numbering, through a total
 * that does not match the list, through a message that only appears when
 * something is hidden. Each of those is tested here as a negative.
 *
 * The Q3 pack is the fixture that does the work. Its stored order interleaves
 * sensitivities deliberately (investor, restricted, investor, confidential,
 * internal) so that filtering at any level removes items from the *middle*. A
 * fixture with the restricted documents at the end would pass a renumbering test
 * while doing no renumbering at all — the same trap as seeding two clearance
 * values identically and calling it a membership test.
 */

const Q3 = "pack-q3-v2";

describe("board pack clearance filtering", () => {
  it("gives a founder every item in stored order", async () => {
    const pack = await packsApi.get(Q3, { clearance: RESTRICTED_CLEARANCE });
    expect(pack).not.toBeNull();
    expect(pack!.items.map((i) => i.document_id)).toEqual([
      "doc-q3-deck",
      "doc-comp",
      "doc-kpi",
      "doc-seriesb-term",
      "doc-pricing-memo",
    ]);
  });

  it("drops documents above the caller's clearance entirely", async () => {
    const pack = await packsApi.get(Q3, { clearance: INVESTOR_CLEARANCE });
    const ids = pack!.items.map((i) => i.document_id);

    expect(ids).toEqual(["doc-q3-deck", "doc-kpi"]);
    // Not redacted, not a placeholder — absent. Nothing in the payload should
    // mention the restricted rows in any form.
    expect(JSON.stringify(pack)).not.toContain("doc-comp");
    expect(JSON.stringify(pack)).not.toContain("doc-seriesb-term");
    expect(JSON.stringify(pack)).not.toContain("pi-q3-2");
  });

  it("renumbers positions to 1..N with no gaps, at every clearance level", async () => {
    for (const clearance of [
      INVESTOR_CLEARANCE,
      INTERNAL_CLEARANCE,
      RESTRICTED_CLEARANCE,
    ]) {
      const pack = await packsApi.get(Q3, { clearance });
      const positions = pack!.items.map((i) => i.position);
      // The contiguity check is the whole point: a hole at position 2 would tell
      // an investor that a document exists between the deck and the KPI pack.
      expect(positions).toEqual(positions.map((_, idx) => idx + 1));
    }
  });

  it("gives the same item a different position at a different clearance", async () => {
    // pi-q3-3 is stored at position 3. An investor cannot see the item stored at
    // position 2, so for them it is item 2. Two readers, one row, two ordinals —
    // which is precisely why position must never be used as an identifier.
    const founder = await packsApi.get(Q3, { clearance: RESTRICTED_CLEARANCE });
    const investor = await packsApi.get(Q3, { clearance: INVESTOR_CLEARANCE });

    const asFounder = founder!.items.find((i) => i.id === "pi-q3-3");
    const asInvestor = investor!.items.find((i) => i.id === "pi-q3-3");

    expect(asFounder!.position).toBe(3);
    expect(asInvestor!.position).toBe(2);
    // The id is what is stable across the two views.
    expect(asFounder!.id).toBe(asInvestor!.id);
  });

  it("exposes no total, count, or withheld field a caller could subtract from", async () => {
    const pack = await packsApi.get(Q3, { clearance: INVESTOR_CLEARANCE });
    const keys = Object.keys(pack!);

    // If a future change adds any of these to the read model, the withheld count
    // becomes derivable and this surface's guarantee is gone.
    for (const forbidden of [
      "item_count",
      "total_items",
      "withheld",
      "withheld_count",
      "hidden_items",
      "total",
    ]) {
      expect(keys).not.toContain(forbidden);
    }
    // The only length available is the length of what was returned.
    expect(pack!.items).toHaveLength(2);
  });

  it("makes an all-withheld pack indistinguishable from an empty one", async () => {
    // pack-seq holds exactly one confidential document. To an investor it is an
    // empty pack, and nothing in the payload says otherwise.
    const pack = await packsApi.get("pack-seq", { clearance: INVESTOR_CLEARANCE });
    expect(pack!.items).toEqual([]);
    expect(JSON.stringify(pack)).not.toContain("doc-seriesb-term");
  });
});

describe("board pack list contract", () => {
  it("orders by version_no DESC then created_at DESC, mirroring list_packs", async () => {
    const packs = await packsApi.list({
      clearance: RESTRICTED_CLEARANCE,
      meeting_id: "m-q3",
    });
    expect(packs.map((p) => p.id)).toEqual(["pack-q3-v2", "pack-q3-v1"]);
  });

  it("filters by meeting and by status", async () => {
    const drafts = await packsApi.list({
      clearance: RESTRICTED_CLEARANCE,
      status: "draft",
    });
    expect(drafts.every((p) => p.status === "draft")).toBe(true);

    const m14 = await packsApi.list({ clearance: RESTRICTED_CLEARANCE, meeting_id: "m-14" });
    expect(m14.every((p) => p.meeting_id === "m-14")).toBe(true);
  });

  it("returns null for a pack that does not exist", async () => {
    expect(await packsApi.get("pack-nope", { clearance: RESTRICTED_CLEARANCE })).toBeNull();
  });
});

describe("supersession", () => {
  it("resolves superseded_by_id to the replacing pack", async () => {
    const packs = await packsApi.list({
      clearance: RESTRICTED_CLEARANCE,
      meeting_id: "m-q3",
    });
    const v1 = packs.find((p) => p.id === "pack-q3-v1")!;
    expect(supersededBy(v1, packs)!.id).toBe("pack-q3-v2");
  });

  it("returns null when the replacement is not in the caller's set", () => {
    const orphan = {
      id: "p1",
      superseded_by_id: "p2-invisible",
    } as BoardPack;
    // A reader may hold a pack whose replacement they cannot see. That is a
    // legitimate state, not an error, so it must not throw.
    expect(supersededBy(orphan, [orphan])).toBeNull();
  });
});

describe("isEditable mirrors the backend lock rules", () => {
  const draft = { status: "draft" } as BoardPack;
  const published = { status: "published" } as BoardPack;

  it("locks a published pack regardless of meeting status", () => {
    expect(isEditable(published, "draft")).toBe(false);
    expect(isEditable(published, "scheduled")).toBe(false);
  });

  it("locks a draft pack once the meeting is no longer pre-meeting", () => {
    for (const status of PACK_LOCKED_MEETING_STATUSES) {
      expect(isEditable(draft, status)).toBe(false);
    }
  });

  it("allows a draft pack on a pre-meeting meeting", () => {
    expect(isEditable(draft, "draft")).toBe(true);
    expect(isEditable(draft, "scheduled")).toBe(true);
  });

  it("fails closed when the meeting status is unknown", () => {
    // Not knowing the parent's state is not permission to edit.
    expect(isEditable(draft, undefined)).toBe(false);
  });

  it("uses the backend's meeting statuses, not the frontend meetings mock", () => {
    // meridian/packs.py:45 locks on cancelled; lib/meetings.ts has never had it.
    // Binding the lock rule to that mock would silently unlock cancelled meetings.
    expect(PACK_LOCKED_MEETING_STATUSES.has("cancelled")).toBe(true);
    expect(PACK_LOCKED_MEETING_STATUSES.has("review")).toBe(false);
    expect(PACK_LOCKED_MEETING_STATUSES.has("archived")).toBe(false);
  });
});

describe("document resolution", () => {
  it("pairs each item with its document", async () => {
    const pack = await packsApi.get(Q3, { clearance: INVESTOR_CLEARANCE });
    const docs = await documentsApi.list({ clearance: INVESTOR_CLEARANCE });
    const rows = resolveItems(pack!.items, docs);

    expect(rows).toHaveLength(2);
    expect(rows[0].document!.title).toBe("Q3 FY26 board deck");
  });

  it("marks a dangling reference as unresolved rather than withheld", () => {
    const item = {
      id: "x",
      board_pack_id: Q3,
      document_id: "doc-does-not-exist",
      agenda_item_id: null,
      position: 1,
      note: null,
      created_at: "2026-07-13T11:05:00Z",
      workspace_id: "w",
    };
    // A broken link is not a hidden document. Conflating them would invent a
    // withheld record where there is only a bad reference.
    expect(resolveItems([item], [])[0].document).toBeNull();
  });

  it("does not act as an existence oracle", async () => {
    // A document above the caller's clearance and a document that was never
    // ingested must be indistinguishable — both null, neither throwing.
    const overClearance = await documentsApi.get("doc-comp", {
      clearance: INVESTOR_CLEARANCE,
    });
    const nonExistent = await documentsApi.get("doc-imaginary", {
      clearance: INVESTOR_CLEARANCE,
    });
    expect(overClearance).toBeNull();
    expect(nonExistent).toBeNull();
  });

  it("never lists a document above the caller's clearance", async () => {
    const docs = await documentsApi.list({ clearance: INVESTOR_CLEARANCE });
    expect(docs.every((d) => d.sensitivity <= INVESTOR_CLEARANCE)).toBe(true);
  });
});
