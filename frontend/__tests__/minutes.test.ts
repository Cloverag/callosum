/**
 * @jest-environment node
 */
import {
  MINUTES_LOCKED_MEETING_STATUSES,
  current,
  isEditable,
  minutesApi,
  supersededBy,
  type Minutes,
} from "../src/lib/minutes";
import { PACK_LOCKED_MEETING_STATUSES } from "../src/lib/packs";
import { MINUTES_FIXTURES } from "../test-support/minutes-fixture";

/**
 * Minutes have a smaller contract than board packs — no clearance, no items —
 * so these tests concentrate on the two things that are easy to get wrong:
 * which record currently stands, and when the record is locked.
 *
 * The lock set gets the most attention because it is the *inverse* of the pack
 * one. A reader skimming both modules could reasonably assume they share a rule;
 * they do not, and a copied lock set would let minutes be written for a meeting
 * that has not happened.
 *
 * `fetch` is stubbed as of CP-C: whether the endpoint returns the right rows is
 * `tests/test_minutes_api.py`'s job against a real Postgres.
 */

let calls: string[] = [];

function stub(payload: unknown = MINUTES_FIXTURES, status = 200) {
  calls = [];
  global.fetch = jest.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    calls.push(url);
    const single = url.match(/\/api\/minutes\/([^?]+)$/);
    if (single) {
      const found = MINUTES_FIXTURES.find((m) => m.id === decodeURIComponent(single[1]));
      return found
        ? new Response(JSON.stringify(found), { status: 200 })
        : new Response(JSON.stringify({ error: { code: "not_found", detail: "gone" } }), { status: 404 });
    }
    // The server scopes by meeting; the stub does too, so the ordering assertion
    // below is about ordering rather than about which rows came back.
    const wanted = new URL(url, "http://localhost").searchParams.get("meeting_id");
    const rows = Array.isArray(payload) && wanted
      ? (payload as typeof MINUTES_FIXTURES)
          .filter((m) => m.meeting_id === wanted)
          // The server orders version_no DESC, created_at DESC.
          .sort((a, b) => b.version_no - a.version_no || b.created_at.localeCompare(a.created_at))
      : payload;
    return new Response(JSON.stringify(rows), { status });
  }) as unknown as typeof fetch;
}

const MEETING = { meeting_id: "m-q3" };

beforeEach(() => stub());
afterEach(() => jest.restoreAllMocks());

describe("minutes list contract", () => {
  it("orders by version_no DESC then created_at DESC, mirroring list_minutes", async () => {
    const records = await minutesApi.list(MEETING);
    expect(records.map((m) => m.id)).toEqual(["min-q3-v2", "min-q3-v1"]);
  });

  it("scopes the request to a meeting and offers no status filter", async () => {
    // `list_minutes` requires a meeting and has never had a status filter. The mock
    // made the first optional and invented the second; offering a capability the
    // backend cannot honour is the same defect as inventing a field.
    await minutesApi.list(MEETING);
    expect(calls[0]).toBe("/api/minutes?meeting_id=m-q3");
    expect(calls[0]).not.toContain("status");
    expect(calls[0]).not.toContain("clearance");
  });

  it("returns every version, not just the one that stands", async () => {
    // The correction trail is the point of this surface; a list showing only the
    // current record would hide exactly what a board needs to reconstruct.
    const records = await minutesApi.list(MEETING);
    expect(records.length).toBeGreaterThan(1);
    expect(records.some((m) => m.superseded_by_id !== null)).toBe(true);
  });

  it("returns null for a record that does not exist", async () => {
    expect(await minutesApi.get("min-nope")).toBeNull();
  });

  it("takes no clearance argument, because meridian/minutes.py takes none", async () => {
    // Minutes are workspace-scoped only: the table has no sensitivity column and
    // no function in the module accepts a clearance. A clearance parameter here
    // would imply a filter the backend does not apply.
    const records = await minutesApi.list(MEETING);
    expect(records.length).toBeGreaterThan(0);
    // Nothing in the read model describes an access level.
    for (const key of ["clearance", "sensitivity", "withheld"]) {
      expect(Object.keys(records[0])).not.toContain(key);
    }
  });
});

describe("which record stands", () => {
  it("returns the highest un-superseded version for a meeting", async () => {
    const all = MINUTES_FIXTURES;
    // m-q3 holds a finalised v1 that was corrected by a draft v2. The draft is
    // what stands, even though it is not final — a correction in progress is
    // still the most current account.
    expect(current(all, "m-q3")!.id).toBe("min-q3-v2");
  });

  it("ignores superseded records even when they are the only final ones", async () => {
    const all = MINUTES_FIXTURES;
    expect(current(all, "m-q3")!.status).toBe("draft");
    expect(current(all, "m-q3")!.superseded_by_id).toBeNull();
  });

  it("returns the single record when a meeting has only one", async () => {
    const all = MINUTES_FIXTURES;
    expect(current(all, "m-14")!.id).toBe("min-m14-v1");
  });

  it("returns null for a meeting with no minutes", async () => {
    const all = MINUTES_FIXTURES;
    expect(current(all, "m-never-happened")).toBeNull();
  });
});

describe("supersession", () => {
  it("resolves superseded_by_id to the correcting record", async () => {
    const all = MINUTES_FIXTURES;
    const v1 = all.find((m) => m.id === "min-q3-v1")!;
    expect(supersededBy(v1, all)!.id).toBe("min-q3-v2");
  });

  it("returns null when the replacement is not in the caller's set", () => {
    const orphan = { id: "m1", superseded_by_id: "m2-missing" } as Minutes;
    expect(supersededBy(orphan, [orphan])).toBeNull();
  });
});

describe("isEditable mirrors the backend lock rules", () => {
  const draft = { status: "draft" } as Minutes;
  const final = { status: "final" } as Minutes;

  it("locks a finalised record regardless of meeting status", () => {
    expect(isEditable(final, "in_progress")).toBe(false);
    expect(isEditable(final, "completed")).toBe(false);
  });

  it("locks a draft record while the meeting has not started", () => {
    for (const status of MINUTES_LOCKED_MEETING_STATUSES) {
      expect(isEditable(draft, status)).toBe(false);
    }
  });

  it("allows a draft record on a live or completed meeting", () => {
    expect(isEditable(draft, "in_progress")).toBe(true);
    expect(isEditable(draft, "completed")).toBe(true);
  });

  it("fails closed when the meeting status is unknown", () => {
    expect(isEditable(draft, undefined)).toBe(false);
  });
});

describe("the minutes and pack lock sets are inverses, deliberately", () => {
  it("locks minutes exactly where packs are editable, and the reverse", () => {
    // A pack is prepared before a meeting and freezes when it starts; minutes are
    // written during or after one and cannot exist before it. If these two sets
    // ever coincide, one of them has been copied from the other by mistake.
    expect(MINUTES_LOCKED_MEETING_STATUSES.has("draft")).toBe(true);
    expect(PACK_LOCKED_MEETING_STATUSES.has("draft")).toBe(false);

    expect(MINUTES_LOCKED_MEETING_STATUSES.has("in_progress")).toBe(false);
    expect(PACK_LOCKED_MEETING_STATUSES.has("in_progress")).toBe(true);

    expect(MINUTES_LOCKED_MEETING_STATUSES.has("completed")).toBe(false);
    expect(PACK_LOCKED_MEETING_STATUSES.has("completed")).toBe(true);
  });

  it("locks both on a cancelled meeting", () => {
    // The one status they agree on: a meeting that never happened has neither a
    // valid pre-read nor a record.
    expect(MINUTES_LOCKED_MEETING_STATUSES.has("cancelled")).toBe(true);
    expect(PACK_LOCKED_MEETING_STATUSES.has("cancelled")).toBe(true);
  });

  it("uses the backend's meeting statuses, not the frontend meetings mock", () => {
    // lib/meetings.ts declares review and archived, which the domain has never
    // had, and omits cancelled, which it does have. See issue #47.
    expect(MINUTES_LOCKED_MEETING_STATUSES.has("review")).toBe(false);
    expect(MINUTES_LOCKED_MEETING_STATUSES.has("archived")).toBe(false);
  });
});
