/**
 * @jest-environment node
 */
import {
  PACK_LOCKED_MEETING_STATUSES,
  isEditable,
  packsApi,
  resolveItems,
  supersededBy,
  type BoardPack,
  type BoardPackItem,
} from "../src/lib/packs";
import { ApiError } from "../src/lib/http";

/**
 * These used to vary `clearance` against an in-memory mock to prove that withheld
 * items leave no gap. **That proof moved to the backend**, where the filtering now
 * happens: `tests/test_packs_api.py` reads the same pack as two principals with
 * different clearances and asserts both get contiguous positions.
 *
 * What is left here is what a client can still get wrong: reintroducing a total,
 * treating `position` as an identity, or offering a way to name a clearance. The
 * last one is the reason `packsApi.list` has no `clearance` argument — a client that
 * could name its own could ask for every restricted document in the workspace.
 */

let calls: string[] = [];

function stub(payload: unknown, status = 200) {
  calls = [];
  global.fetch = jest.fn(async (input: RequestInfo | URL) => {
    calls.push(String(input));
    return new Response(JSON.stringify(payload), { status });
  }) as unknown as typeof fetch;
}

/** A pack as the server serialises it: already filtered, already renumbered. */
function serverPack(items: Partial<BoardPackItem>[]): BoardPack {
  return {
    id: "pack-q3",
    meeting_id: "m-q3",
    title: "Q3 FY26 board pack",
    status: "published",
    version_no: 1,
    superseded_by_id: null,
    published_at: "2026-07-14T09:00:00Z",
    version: 4,
    created_at: "2026-07-13T11:00:00Z",
    updated_at: "2026-07-14T09:00:00Z",
    workspace_id: "w",
    items: items.map((item, i) => ({
      id: `pi-${i + 1}`,
      board_pack_id: "pack-q3",
      document_id: `doc-${i + 1}`,
      agenda_item_id: null,
      position: i + 1,
      note: null,
      created_at: "2026-07-13T11:05:00Z",
      workspace_id: "w",
      ...item,
    })) as BoardPackItem[],
  };
}

describe("the client cannot name a clearance", () => {
  it("list takes a meeting and a status, and nothing else", async () => {
    stub([]);
    await packsApi.list({ meeting_id: "m-q3", status: "published" });
    expect(calls[0]).toBe("/api/packs?meeting_id=m-q3&status=published");
    // ADR-013: clearance is resolved from the caller's membership on the server.
    expect(calls[0]).not.toContain("clearance");
  });

  it("get sends no clearance either", async () => {
    stub(serverPack([{}]));
    await packsApi.get("pack-q3");
    expect(calls[0]).toBe("/api/packs/pack-q3");
  });
});

describe("the response carries nothing to subtract from", () => {
  it("has no total, count or withheld field", async () => {
    stub(serverPack([{}, {}]));
    const pack = (await packsApi.get("pack-q3"))!;
    for (const forbidden of [
      "item_count",
      "total_items",
      "withheld",
      "withheld_count",
      "hidden_items",
      "total",
    ]) {
      expect(Object.keys(pack)).not.toContain(forbidden);
    }
    // The only length available is the length of what arrived.
    expect(pack.items).toHaveLength(2);
  });

  it("renders an all-withheld pack identically to an empty one", async () => {
    // The server returns an empty item list either way, and the client must not be
    // able to tell the difference — that indistinguishability is the guarantee.
    stub(serverPack([]));
    const pack = (await packsApi.get("pack-q3"))!;
    expect(pack.items).toEqual([]);
    expect(JSON.stringify(pack)).not.toContain("withheld");
  });

  it("does not renumber or re-sort what the server sent", async () => {
    // Renumbering is the server's, and doing it again here would be a second
    // implementation of the property that can disagree with the first.
    stub(serverPack([{}, {}, {}]));
    const pack = (await packsApi.get("pack-q3"))!;
    expect(pack.items.map((i) => i.position)).toEqual([1, 2, 3]);
    expect(pack.items.map((i) => i.id)).toEqual(["pi-1", "pi-2", "pi-3"]);
  });
});

describe("position is an ordinal, not an identity", () => {
  it("resolveItems keys off the document id rather than the position", () => {
    const items = serverPack([{ document_id: "doc-a" }, { document_id: "doc-b" }]).items;
    const rows = resolveItems(items, [
      { id: "doc-b", title: "B", doc_type: "memo", source_uri: null, sensitivity: 2, authored_at: null, ingested_at: "x" },
    ]);
    // Position 1 resolves to nothing and position 2 resolves — which only works if
    // the lookup is by id.
    expect(rows[0].document).toBeNull();
    expect(rows[1].document!.title).toBe("B");
  });

  it("marks a dangling reference as unresolved rather than withheld", () => {
    // A broken link is not a hidden document. Conflating them would invent a
    // withheld record where there is only a bad reference.
    const items = serverPack([{ document_id: "doc-missing" }]).items;
    expect(resolveItems(items, [])[0].document).toBeNull();
  });
});

describe("lock rules mirror the backend", () => {
  const draft = { status: "draft" } as BoardPack;

  it("locks a published pack regardless of meeting status", () => {
    expect(isEditable({ status: "published" } as BoardPack, "draft")).toBe(false);
  });

  it("locks a draft once the meeting is no longer pre-meeting", () => {
    for (const status of PACK_LOCKED_MEETING_STATUSES) {
      expect(isEditable(draft, status)).toBe(false);
    }
  });

  it("fails closed when the meeting status is unknown", () => {
    expect(isEditable(draft, undefined)).toBe(false);
  });

  it("still includes cancelled — the status #47 had missing", () => {
    expect(PACK_LOCKED_MEETING_STATUSES.has("cancelled")).toBe(true);
  });
});

describe("supersession and errors", () => {
  it("returns null when the replacement is not in the caller's set", () => {
    const orphan = { id: "p1", superseded_by_id: "p2-invisible" } as BoardPack;
    expect(supersededBy(orphan, [orphan])).toBeNull();
  });

  it("returns null for a missing pack and throws when refused", async () => {
    stub({ error: { code: "not_found", detail: "gone" } }, 404);
    expect(await packsApi.get("pack-nope")).toBeNull();

    stub({ error: { code: "forbidden", detail: "Not available to you." } }, 403);
    await expect(packsApi.get("pack-q3")).rejects.toBeInstanceOf(ApiError);
  });
});
