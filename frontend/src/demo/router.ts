import type { AuthContext } from "@/lib/auth";
import { AGENDA_ITEMS, MEETINGS } from "./fixtures/meetings";
import { BOARD_MEMBERS } from "./fixtures/people";
import { DOCUMENTS, QUARANTINE_ITEMS } from "./fixtures/documents";
import {
  COMMITMENTS, CONFLICTS, DECISIONS, MINUTES_SET, PACKS, RESOLUTIONS,
} from "./fixtures/governance";
import {
  DEMO_PRINCIPAL_ID, DEMO_PRINCIPAL_NAME, DEMO_PRINCIPAL_ROLE, DEMO_WORKSPACE_ID,
} from "./fixtures/ids";

/**
 * The one place a request can be answered from fixtures instead of from the API.
 *
 * ---------------------------------------------------------------------------
 * WHY THERE IS EXACTLY ONE OF THESE
 * ---------------------------------------------------------------------------
 * `lib/api.ts` records what the previous mock layer did. Every method had the
 * shape `if (res.ok) return await res.json(); ... return mockConflicts.filter(...)`.
 * `GET /api/conflicts` then 500ed for four days and nothing on screen said so:
 * the dashboard read the fallback and told the operator "2 name conflicts
 * awaiting your review", by name, as measured fact. rules.md §2 forbids that.
 *
 * The defect was not that mocks existed. It was that the mock lived *inside the
 * error path*, so the condition for showing invented data was the API failing —
 * exactly the moment the operator most needed to be told something was wrong.
 *
 * So this module is arranged to make that unreachable:
 *
 *   1. It is entered on `DEMO_ENABLED` alone — a build-time constant read from
 *      the environment before any request is made. It is never entered from a
 *      response, a status code, a thrown error or a timeout.
 *   2. There is no `catch` in this file and no reference to `fetch`. It cannot
 *      call the network, so it cannot react to the network failing.
 *   3. An unknown route returns a **500 carrying an error envelope**, not an
 *      empty list. A surface that asks for something the fixtures do not cover
 *      shows a visible failure, the same as it would against a broken API. The
 *      failure mode of incomplete demo data is a red panel, never a plausible
 *      empty one — an empty list is a claim ("there are none") and a fixture
 *      set has no standing to make it.
 *
 * `__tests__/demo-mode.test.ts` asserts 1, 2 and 3, and that the banner is
 * driven by the same constant as the interception.
 *
 * ---------------------------------------------------------------------------
 * WHY IT RETURNS A `Response`
 * ---------------------------------------------------------------------------
 * Rather than returning parsed objects, it hands back a real `Response` and lets
 * `lib/http.ts` parse it exactly as it parses the server's. `toApiError`, the
 * 204 branch, `apiGetOrNull`'s 404 handling and the `ApiError` taxonomy are all
 * the same code on both paths. A demo mode that bypassed them would be
 * exercising a different client than the one that ships.
 */

const json = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

/** The shape `meridian/api/errors.py` emits, so `toApiError` reads it normally. */
const fail = (status: number, code: string, detail: string): Response =>
  json({ error: { code, detail } }, status);

/**
 * The demo session.
 *
 * Present for the same reason the fixtures are: `SessionGate` renders the shell
 * only for a session that has both a principal and a workspace, so with no
 * backend nobody reaches any of the thirteen pages at all. The name and role are
 * not a person and not one of `BoardRole`'s values — see `fixtures/ids.ts`.
 */
const CONTEXT: AuthContext = {
  principal_id: DEMO_PRINCIPAL_ID,
  name: DEMO_PRINCIPAL_NAME,
  role: DEMO_PRINCIPAL_ROLE,
  clearance: 4,
  workspace_id: DEMO_WORKSPACE_ID,
};

type Handler = (params: URLSearchParams, segments: string[], body: unknown) => Response;

/** `true` unless the caller filtered on this field and the row does not match. */
const matches = (params: URLSearchParams, key: string, value: string | null): boolean => {
  const wanted = params.get(key);
  return wanted === null || wanted === value;
};

const byId = <T extends { id: string }>(rows: T[], id: string): Response => {
  const row = rows.find((r) => r.id === id);
  // 404 rather than an empty object: `apiGetOrNull` turns exactly this into
  // `null`, which is the "not found" state every detail surface already renders.
  return row ? json(row) : fail(404, "not_found", "No such record in the demo fixtures.");
};

/**
 * Routes, keyed by `METHOD /first-segment`.
 *
 * Matching on the first segment with the rest passed through as `segments`
 * keeps this a lookup rather than a chain of regexes, and means an unrouted
 * path falls off the end into the 500 instead of into a near-miss.
 */
const ROUTES: Record<string, Handler> = {
  "GET /meetings": (p) =>
    json(MEETINGS.filter((m) => matches(p, "status", m.status))),

  "GET /meetings/:id": (_p, s) => {
    if (s.length === 2 && s[1] === "material") {
      const assigned = s[0] === MEETINGS[2].id ? DOCUMENTS.slice(3, 5) : DOCUMENTS.slice(0, 2);
      return json({ documents: assigned, withheld: s[0] === MEETINGS[0].id ? 1 : 0 });
    }
    if (s.length > 1) return fail(500, "demo_route_missing", `No demo fixture for /meetings/${s.join("/")}.`);
    return byId(MEETINGS, s[0]);
  },

  "GET /agenda": (p) =>
    json(AGENDA_ITEMS.filter((a) => matches(p, "meeting_id", a.meeting_id))),

  "GET /agenda/:id": (_p, s) => byId(AGENDA_ITEMS, s[0]),

  "GET /board-members": (p) => {
    const active = p.get("active");
    return json(
      BOARD_MEMBERS.filter((m) => {
        if (active === null || active === "all") return true;
        return String(m.active) === active;
      }).filter((m) => matches(p, "role", m.role)),
    );
  },

  "GET /board-members/:id": (_p, s) => byId(BOARD_MEMBERS, s[0]),

  "GET /packs": (p) =>
    json(
      PACKS.filter((k) => matches(p, "meeting_id", k.meeting_id))
        .filter((k) => matches(p, "status", k.status)),
    ),

  "GET /packs/:id": (_p, s) => byId(PACKS, s[0]),

  "GET /minutes": (p) =>
    json(MINUTES_SET.filter((m) => matches(p, "meeting_id", m.meeting_id))),

  "GET /minutes/:id": (_p, s) => byId(MINUTES_SET, s[0]),

  "GET /decisions": (p) =>
    json(
      DECISIONS.filter((d) => matches(p, "meeting_id", d.meeting_id))
        .filter((d) => matches(p, "status", d.status)),
    ),

  "GET /decisions/:id": (_p, s) => byId(DECISIONS, s[0]),

  "GET /resolutions": (p) =>
    json(
      RESOLUTIONS.filter((r) => matches(p, "decision_id", r.decision_id))
        .filter((r) => matches(p, "status", r.status)),
    ),

  "GET /resolutions/:id": (_p, s) => byId(RESOLUTIONS, s[0]),

  "GET /commitments": (p) => {
    const openOnly = p.get("open_only") === "true";
    return json(
      COMMITMENTS.filter((c) => matches(p, "decision_id", c.decision_id))
        .filter((c) => matches(p, "owner_board_member_id", c.owner_board_member_id))
        .filter((c) => matches(p, "status", c.status))
        .filter((c) => !openOnly || (c.status !== "completed" && c.status !== "cancelled")),
    );
  },

  "GET /commitments/:id": (_p, s) => byId(COMMITMENTS, s[0]),

  "GET /documents": (p) =>
    json(DOCUMENTS.filter((d) => matches(p, "doc_type", d.doc_type))),

  "GET /documents/:id": (_p, s) => {
    if (s[0] === "quarantine") return json(QUARANTINE_ITEMS);
    if (s.length === 2 && s[1] === "versions") {
      // Walk to the root of this document's chain, then forward, so the panel
      // gets the whole lineage whichever revision it was asked about.
      let root = DOCUMENTS.find((d) => d.id === s[0]);
      if (!root) return fail(404, "not_found", "No such document in the demo fixtures.");
      for (;;) {
        const earlier = DOCUMENTS.find((d) => d.superseded_by_id === root!.id);
        if (!earlier) break;
        root = earlier;
      }
      const revisions = [root];
      for (;;) {
        const next = DOCUMENTS.find((d) => d.id === revisions[revisions.length - 1].superseded_by_id);
        if (!next) break;
        revisions.push(next);
      }
      const current = revisions[revisions.length - 1];
      return json({ revisions, withheld: 0, current_id: current.id });
    }
    if (s.length > 1) return fail(500, "demo_route_missing", `No demo fixture for /documents/${s.join("/")}.`);
    return byId(DOCUMENTS, s[0]);
  },

  "GET /conflicts": (p) =>
    json(CONFLICTS.filter((c) => matches(p, "status", c.status))),

  "GET /auth/context": () => json(CONTEXT),
  "POST /auth/workspace": () => json({ status: "ok", workspace_id: DEMO_WORKSPACE_ID }),
  "POST /auth/logout": () => json({ status: "signed_out" }),
};

/**
 * Writes are refused, not simulated.
 *
 * The write paths were the worse half of the old mock layer: `approveConflict`
 * caught the failure, mutated a module-level array and returned
 * `{ status: 'approved' }`, so the card animated away and the operator was told
 * a merge had been recorded into an append-only graph that had not been touched.
 *
 * A demo that accepts writes has to either lie about persistence or pretend to
 * a durability it does not have. A 405 with an honest reason is the only answer
 * that is true. The maintainer asked to see what the dashboard *looks like*;
 * that is a question about reads.
 */
const WRITE_REFUSED = fail.bind(
  null,
  405,
  "demo_read_only",
  "Demo mode serves fixtures and does not record writes. Run against the API to make changes.",
);

/**
 * Answer a request from fixtures. Never touches the network.
 *
 * @param url    the same string `fetch` would have been given
 * @param method the HTTP method
 * @param body   the serialised request body, if any — accepted so handlers may
 *               read it, unused today because every write is refused
 */
export function demoResponse(url: string, method: string, body: unknown): Response {
  // A relative URL needs a base to parse; the base is discarded. `example.invalid`
  // is reserved by RFC 2606 and can never resolve, so nothing can accidentally
  // treat this as an address.
  const parsed = new URL(url, "https://demo.example.invalid");
  const segments = parsed.pathname.split("/").filter(Boolean);

  if (method !== "GET") {
    // `/auth` POSTs are the session, not domain writes — they are how the gate
    // opens, and refusing them would mean demo mode could not be entered.
    const authRoute = ROUTES[`${method} /${segments.join("/")}`];
    if (authRoute) return authRoute(parsed.searchParams, [], body);
    return WRITE_REFUSED();
  }

  // `/api/x` and `/auth/x` are both mounted, and they are not the same shape.
  // `/api` is a base prefix that no route key contains, so it is dropped and the
  // collection is the next segment. `/auth` IS part of its keys, so both
  // segments are the key. Splitting the path once, here, is what lets every
  // route below be a plain lookup.
  const isApi = segments[0] === "api";
  const key = isApi ? `/${segments[1] ?? ""}` : `/${segments.slice(0, 2).join("/")}`;
  const rest = segments.slice(2);

  const handler = rest.length === 0 ? ROUTES[`GET ${key}`] : ROUTES[`GET ${key}/:id`];
  if (handler) return handler(parsed.searchParams, rest, body);

  return fail(
    500,
    "demo_route_missing",
    `Demo mode has no fixture for GET ${parsed.pathname}. This is a gap in the ` +
      `demo dataset, not an API error — the surface is showing you a real absence.`,
  );
}
