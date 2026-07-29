/**
 * @jest-environment node
 *
 * Node rather than jsdom, deliberately. This file renders nothing — it exercises the
 * API client — and the Node environment provides the real `Response` and `fetch`
 * globals that the Fetch API is specified against. jsdom shadows them with nothing,
 * which would leave the stub asserting against a hand-written shim rather than
 * against the objects the browser will actually hand the client.
 */
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
import { ApiError } from "../src/lib/http";
import { RESOLUTION_FIXTURES } from "../test-support/resolutions-fixture";
import { BOARD_MEMBER_FIXTURES } from "../test-support/board-members-fixture";

/**
 * `fetch` is stubbed rather than a backend being started.
 *
 * These are client tests: they check that `resolutionsApi` builds the right request,
 * preserves the server's ordering, and turns a 404 into `null`. Whether the endpoint
 * returns the right rows is `tests/test_resolutions_api.py`'s job, against a real
 * Postgres — asking this suite to prove it again would make it slow, non-deterministic
 * and dependent on a running server for no coverage gained.
 *
 * The fixtures are the data the in-memory mock used to hold, so every contract
 * assertion below is unchanged from when it ran against that mock.
 */

type StubbedCall = { url: string; init?: RequestInit };

let calls: StubbedCall[] = [];

/** Serves the fixtures the way the real API does, including filters and 404s. */
function stubFetch(payload: Resolution[] = RESOLUTION_FIXTURES) {
  calls = [];
  global.fetch = jest.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });

    // The directory is a real client as of CP-C, so these tests stub it too. `active`
    // is honoured because the "inactive members still resolve" assertion depends on
    // the caller asking for all of them.
    if (url.startsWith("/api/board-members")) {
      const wanted = new URL(url, "http://localhost").searchParams.get("active");
      const rows =
        wanted === "all"
          ? BOARD_MEMBER_FIXTURES
          : BOARD_MEMBER_FIXTURES.filter((m) => m.active === (wanted !== "false"));
      return new Response(JSON.stringify(rows), { status: 200 });
    }

    const single = url.match(/\/api\/resolutions\/([^?]+)$/);
    if (single) {
      const found = payload.find((r) => r.id === decodeURIComponent(single[1]));
      return found
        ? new Response(JSON.stringify(found), { status: 200 })
        : new Response(JSON.stringify({ error: { code: "not_found", detail: "gone" } }), { status: 404 });
    }

    // The server orders by version_no DESC, created_at DESC and applies the filters.
    const params = new URL(url, "http://localhost").searchParams;
    let rows = [...payload];
    const decision = params.get("decision_id");
    const status = params.get("status");
    if (decision) rows = rows.filter((r) => r.decision_id === decision);
    if (status) rows = rows.filter((r) => r.status === status);
    rows.sort((a, b) => b.version_no - a.version_no || b.created_at.localeCompare(a.created_at));
    return new Response(JSON.stringify(rows), { status: 200 });
  }) as unknown as typeof fetch;
}

/** Makes every request fail with the API's error envelope. */
function stubFailure(status: number, code: string, detail = "nope") {
  calls = [];
  global.fetch = jest.fn(async () =>
    new Response(JSON.stringify({ error: { code, detail } }), { status }),
  ) as unknown as typeof fetch;
}

beforeEach(() => stubFetch());
afterEach(() => jest.restoreAllMocks());

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
    const members = await boardMembersApi.list({ active: "all" });
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
    // `active: "all"` replaces the mock's `include_inactive: true` — a parameter the
    // domain never had. `list_members` takes a tri-state, and the two-valued flag
    // silently dropped the departed-only case.
    const active = await boardMembersApi.list();
    const everyone = await boardMembersApi.list({ active: "all" });
    expect(everyone.length).toBeGreaterThan(active.length);
    expect(active.every((m) => m.active)).toBe(true);
  });

  it("can ask for departed members only — the case the old flag could not express", async () => {
    const departed = await boardMembersApi.list({ active: false });
    expect(departed.length).toBeGreaterThan(0);
    expect(departed.every((m) => !m.active)).toBe(true);
  });

  it("defaults to active only, matching the domain default", async () => {
    await boardMembersApi.list();
    expect(calls.at(-1)!.url).toBe("/api/board-members?active=true");
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


// ---------------------------------------------------------------------------
// Client behaviour (CP-B/B3)
//
// What the mock could never be wrong about, and the real client can: the request it
// builds, the credentials it sends, and what it does with a non-2xx response.
// ---------------------------------------------------------------------------

describe("the client builds the right request", () => {
  it("calls the same-origin API path", async () => {
    await resolutionsApi.list();
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe("/api/resolutions");
  });

  it("sends the session cookie", async () => {
    // The session is an httpOnly cookie (ADR-009). A request that omitted it would
    // read as logged-out rather than as misconfigured, which is a confusing bug.
    await resolutionsApi.list();
    expect(calls[0].init?.credentials).toBe("same-origin");
  });

  it("passes filters as query parameters", async () => {
    await resolutionsApi.list({ decision_id: "d-price-adopt", status: "adopted" });
    expect(calls[0].url).toContain("decision_id=d-price-adopt");
    expect(calls[0].url).toContain("status=adopted");
  });

  it("omits absent filters rather than sending empty ones", async () => {
    // `status=` would ask the API to match on the empty string, which is a different
    // request from "no status filter".
    await resolutionsApi.list({ decision_id: "d-seq" });
    expect(calls[0].url).toBe("/api/resolutions?decision_id=d-seq");
  });

  it("has no way to send a workspace_id", async () => {
    // ADR-013. The API derives it from the session and the OpenAPI guard fails the
    // build if an endpoint ever accepts one, so the client offers no option to pass
    // a value that has nowhere legitimate to go.
    await resolutionsApi.list({ decision_id: "d-seq", status: "draft" });
    expect(calls[0].url).not.toContain("workspace");
  });

  it("encodes an id that would otherwise break the path", async () => {
    await resolutionsApi.get("res/../../etc");
    expect(calls[0].url).toBe("/api/resolutions/res%2F..%2F..%2Fetc");
  });
});

describe("the client preserves the server's answer", () => {
  it("does not re-sort what the API returned", async () => {
    // The server orders by version_no DESC, created_at DESC. A second ordering here
    // is a second thing that can disagree with the first.
    const payload = [...RESOLUTION_FIXTURES].reverse();
    global.fetch = jest.fn(async () =>
      new Response(JSON.stringify(payload), { status: 200 }),
    ) as unknown as typeof fetch;

    const got = await resolutionsApi.list();
    expect(got.map((r) => r.id)).toEqual(payload.map((r) => r.id));
  });
});

describe("the client surfaces API errors", () => {
  it("returns null for a missing resolution rather than throwing", async () => {
    // Preserves the mock's contract, so the surfaces that already render an empty
    // state keep working unchanged.
    expect(await resolutionsApi.get("res-does-not-exist")).toBeNull();
  });

  it("throws rather than returning null when access is refused", async () => {
    // Being refused is not the same as it not existing. Collapsing them would hide a
    // permissions problem behind an empty state.
    stubFailure(403, "forbidden", "Not available to you.");
    await expect(resolutionsApi.get("res-seriesb")).rejects.toBeInstanceOf(ApiError);
  });

  it("carries the taxonomy code so callers can branch without parsing prose", async () => {
    stubFailure(409, "stale_resource", "expected version 3, current 4");
    await expect(resolutionsApi.list()).rejects.toMatchObject({
      status: 409,
      code: "stale_resource",
      message: "expected version 3, current 4",
    });
  });

  it("distinguishes a stale write from a bad request", async () => {
    stubFailure(409, "stale_resource");
    const stale = await resolutionsApi.list().catch((e) => e);
    expect(stale.isStale).toBe(true);

    stubFailure(422, "invalid");
    const invalid = await resolutionsApi.list().catch((e) => e);
    expect(invalid.isStale).toBe(false);
  });

  it("flags an unauthenticated session and an unchosen workspace separately", async () => {
    stubFailure(401, "not_authenticated");
    const anon = await resolutionsApi.list().catch((e) => e);
    expect(anon.isUnauthenticated).toBe(true);
    expect(anon.needsWorkspace).toBe(false);

    stubFailure(409, "workspace_not_selected");
    const unchosen = await resolutionsApi.list().catch((e) => e);
    // 409 here means "pick a workspace", not "log in again" — a client that
    // re-authenticated on this would loop.
    expect(unchosen.needsWorkspace).toBe(true);
    expect(unchosen.isUnauthenticated).toBe(false);
  });

  it("still raises an ApiError when the body is not the taxonomy envelope", async () => {
    // A proxy error page or a gateway timeout. A caller handling errors should not
    // also have to handle the error handler failing.
    global.fetch = jest.fn(async () =>
      new Response("<html>502 Bad Gateway</html>", { status: 502 }),
    ) as unknown as typeof fetch;
    const err = await resolutionsApi.list().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(502);
  });
});
