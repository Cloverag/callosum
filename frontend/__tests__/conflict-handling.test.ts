/**
 * @jest-environment node
 */

/**
 * CP-D D3 — the client half of optimistic concurrency.
 *
 * `@jest-environment node` because jsdom shadows `Response` and `fetch` with nothing,
 * so a client test under jsdom asserts against undefined globals rather than against
 * the Fetch API.
 *
 * Two things are tested here, and they fail in opposite directions:
 *
 * 1. **`changesBetween` must omit what did not change.** The API reads an absent field
 *    as "leave alone" and an explicit `null` as "clear". A surface that serialises its
 *    whole form state sends `null` for every empty input and wipes fields nobody
 *    touched. That is silent data loss and it looks like a successful save.
 *
 * 2. **A 409 must be classified, not just caught.** A stale version resolves by
 *    refetching; a locked or illegal-transition refusal never will. Offering "retry"
 *    on the second is a button that cannot work.
 */

import { ApiError, apiDelete, apiPatch, apiPost } from "../src/lib/http";
import { changesBetween, type Meeting } from "../src/lib/meetings";

const MEETING: Meeting = {
  id: "11111111-1111-1111-1111-111111111111",
  workspace_id: "22222222-2222-2222-2222-222222222222",
  title: "Board Meeting 17",
  scheduled_start: "2026-09-01T10:00:00Z",
  scheduled_end: "2026-09-01T11:00:00Z",
  location: "Room A",
  status: "draft",
  version: 3,
  created_by: null,
  created_at: "2026-08-01T09:00:00Z",
  updated_at: "2026-08-01T09:00:00Z",
};

function stubFetch(status: number, body: unknown) {
  const spy = jest.fn(async () =>
    status === 204
      ? new Response(null, { status })
      : new Response(JSON.stringify(body), {
          status,
          headers: { "Content-Type": "application/json" },
        }),
  );
  global.fetch = spy as unknown as typeof fetch;
  return spy;
}

const errorBody = (code: string, detail: string) => ({ error: { code, detail } });

afterEach(() => {
  jest.restoreAllMocks();
});

describe("changesBetween sends only what changed", () => {
  it("omits a field the user did not touch", () => {
    const changes = changesBetween(MEETING, {
      title: "Renamed",
      location: MEETING.location,
    });
    expect(changes).toEqual({ title: "Renamed" });
    expect("location" in changes).toBe(false);
  });

  it("emits null only when a field was actually cleared", () => {
    const changes = changesBetween(MEETING, { location: null });
    expect(changes).toEqual({ location: null });
  });

  it("returns an empty patch when nothing changed", () => {
    // The form calls this on every submit, including ones where the user opened the
    // dialog and pressed save. An empty patch is a 422 from the API, so the caller
    // skips the request entirely rather than asking for an error.
    expect(changesBetween(MEETING, { title: MEETING.title, location: MEETING.location })).toEqual({});
  });

  it("never clears the title", () => {
    // `title` is NOT NULL. An empty one is a form validation error, not an instruction
    // to clear, and sending null would turn a typo into a 422 the user cannot read.
    const changes = changesBetween(MEETING, { title: MEETING.title });
    expect(changes).toEqual({});
  });
});

describe("a 409 is classified, not just caught", () => {
  it("recognises a stale version and recovers both version numbers", async () => {
    stubFetch(409, errorBody("stale_resource", "meeting x: expected version 3, current 4"));

    const error: ApiError = await apiPatch("/meetings/x", { expected_version: 3 }).catch((e) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.isConflict).toBe(true);
    expect(error.isStale).toBe(true);
    expect(error.isUnretryableConflict).toBe(false);
    // The numbers are what let the UI say "you started from 3, it is now 4" instead of
    // "something went wrong".
    expect(error.versions).toEqual({ expected: 3, current: 4 });
  });

  it("marks a locked refusal as unretryable", async () => {
    stubFetch(409, errorBody("conflict", "cannot edit a published board pack"));

    const error: ApiError = await apiPatch("/packs/x", { expected_version: 1 }).catch((e) => e);

    expect(error.isConflict).toBe(true);
    expect(error.isStale).toBe(false);
    expect(error.isUnretryableConflict).toBe(true);
    // No versions to report: refetching changes nothing, so there is nothing to compare.
    expect(error.versions).toBeNull();
  });

  it("does not treat a 422 as a conflict", async () => {
    stubFetch(422, errorBody("invalid", "scheduled_end must be after scheduled_start"));

    const error: ApiError = await apiPost("/meetings", { title: "x" }).catch((e) => e);

    expect(error.status).toBe(422);
    expect(error.isConflict).toBe(false);
    expect(error.isUnretryableConflict).toBe(false);
  });

  it("does not mistake workspace selection for a stale write", async () => {
    // Also a 409, and the only correct response is to choose a workspace — not to
    // refetch a resource and not to show a merge decision.
    stubFetch(409, errorBody("workspace_not_selected", "no workspace selected"));

    const error: ApiError = await apiPost("/meetings", {}).catch((e) => e);

    expect(error.needsWorkspace).toBe(true);
    expect(error.isStale).toBe(false);
    expect(error.isUnretryableConflict).toBe(false);
  });

  it("returns null versions rather than guessing when the detail omits them", async () => {
    stubFetch(409, errorBody("stale_resource", "meeting x was modified"));

    const error: ApiError = await apiPatch("/meetings/x", {}).catch((e) => e);

    expect(error.isStale).toBe(true);
    expect(error.versions).toBeNull();
  });
});

describe("the write helpers", () => {
  it("sends the body as JSON with the session cookie", async () => {
    const spy = stubFetch(201, MEETING);

    await apiPost("/meetings", { title: "Board Meeting 17" });

    const [url, init] = spy.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/meetings");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");
    expect(JSON.parse(init.body as string)).toEqual({ title: "Board Meeting 17" });
  });

  it("puts expected_version in the query string on delete", async () => {
    // A body on DELETE is legal but poorly supported by proxies, so the API takes it
    // as a parameter. If this ever moves, the server test fails too.
    const spy = stubFetch(204, null);

    await apiDelete("/agenda/abc", 2);

    const [url] = spy.mock.calls[0] as unknown as [string];
    expect(url).toBe("/api/agenda/abc?expected_version=2");
  });

  it("does not try to parse a 204 body", async () => {
    // `response.json()` on an empty body throws, which would surface as a crash on a
    // successful delete — the one case where nothing went wrong at all.
    stubFetch(204, null);
    await expect(apiDelete("/agenda/abc", 1)).resolves.toBeUndefined();
  });

  it("surfaces a non-JSON error body as an ApiError rather than a parse failure", async () => {
    // A proxy error page or gateway timeout is still an error the caller has to
    // handle; it must not arrive as a SyntaxError from the error handler itself.
    global.fetch = jest.fn(async () =>
      new Response("<html>502 Bad Gateway</html>", { status: 502 }),
    ) as unknown as typeof fetch;

    const error: ApiError = await apiPost("/meetings", {}).catch((e) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(502);
    expect(error.code).toBe("http_error");
  });
});
