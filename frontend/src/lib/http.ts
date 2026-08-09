/**
 * The HTTP client every `lib/*` module talks to the Meridian API through.
 *
 * Written once here rather than per module, so that error handling, credential
 * behaviour and the response envelope stay identical as CP-C swaps the remaining
 * mocks. A per-module `fetch` is how one surface ends up treating a 409 as a crash
 * while its sibling retries.
 *
 * ---------------------------------------------------------------------------
 * WHAT IS DELIBERATELY ABSENT
 * ---------------------------------------------------------------------------
 * There is no `workspace_id` parameter and no place to pass one. The API derives it
 * from the session cookie on every request (ADR-013), and `tests/test_openapi_input_guard.py`
 * fails the build if an endpoint ever accepts one. A client-side option would be a
 * value with nowhere legitimate to go.
 */

/** Same-origin by construction: Next.js and the API share a host (ADR-009). */
const API_BASE = "/api";

/**
 * A non-2xx response, carrying the server's own error envelope.
 *
 * `code` is the machine-readable half from `meridian/api/errors.py`, and it is the
 * field callers should branch on. The distinction that matters is `stale_resource`
 * (409 — refetch and retry) versus `invalid` (422 — fix the input); both are 4xx and
 * only one is worth retrying, which is not something to infer from prose.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }

  /** True when the caller's copy is out of date and a refetch may succeed. */
  get isStale(): boolean {
    return this.code === "stale_resource";
  }

  /**
   * True when the *state* refused a well-formed request: a stale version, a locked
   * parent, a move the lifecycle does not allow.
   *
   * The distinction from 422 is the whole point of CP-D and is worth stating once
   * here rather than being rediscovered per surface. A 409 means **re-read and
   * reconsider**; a 422 means **change something and resend**. Offering "try again"
   * on a 422 invites the user to resend an identical request forever.
   */
  get isConflict(): boolean {
    return this.status === 409;
  }

  /**
   * True when a 409 will *never* succeed on retry, however fresh the caller's copy.
   *
   * A stale version resolves by refetching. A locked pack, a finalised set of minutes,
   * an illegal transition — those refuse the operation itself, so a surface that
   * offered "reload and retry" would be promising something that cannot happen.
   */
  get isUnretryableConflict(): boolean {
    return this.isConflict && !this.isStale && !this.needsWorkspace;
  }

  /**
   * The two version numbers a stale write reports, when the server included them.
   *
   * `errors.classify` passes the domain's message through verbatim precisely so this
   * is recoverable — "expected version 3, current 4" tells a surface how far behind
   * the user is, which is the difference between "someone else saved" and "someone
   * else saved twice while you were typing".
   *
   * Returns `null` rather than guessing when the message does not carry them: an
   * invented version number is worse than an absent one.
   */
  get versions(): { expected: number; current: number } | null {
    const match = /expected version (\d+), current (\d+)/.exec(this.message);
    if (!match) return null;
    return { expected: Number(match[1]), current: Number(match[2]) };
  }

  /** True when the session needs re-establishing rather than the request retrying. */
  get isUnauthenticated(): boolean {
    return this.status === 401;
  }

  /** True when authenticated but no workspace has been chosen yet. */
  get needsWorkspace(): boolean {
    return this.status === 409 && this.code === "workspace_not_selected";
  }

  /**
   * True when the session is valid but the workspace it selected is not (or no
   * longer) available to this principal.
   *
   * The API returns one uniform 403 for "never a member", "membership revoked"
   * and "that workspace is not yours" — it will not say which, because
   * distinguishing them confirms to a stranger that a workspace id is real.
   * The client cannot tell them apart either, which is exactly why the only
   * sound response is to offer workspace selection again rather than to guess.
   */
  get isForbidden(): boolean {
    return this.status === 403;
  }
}

type Params = Record<string, string | undefined>;

function query(params?: Params): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    // Undefined means "no filter", not "filter by nothing" — sending an empty string
    // would ask the API to match on it.
    if (value !== undefined) search.set(key, value);
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

export async function toApiError(response: Response): Promise<ApiError> {
  // The taxonomy returns {"error": {"code", "detail"}}. Anything else — a proxy error
  // page, a gateway timeout — is still surfaced as an ApiError rather than as a parse
  // failure, because a caller handling errors should not also have to handle the
  // error handler failing.
  try {
    const body = await response.json();
    const error = body?.error;
    if (error?.code) return new ApiError(response.status, error.code, error.detail ?? response.statusText);
    if (body?.detail?.code) return new ApiError(response.status, body.detail.code, body.detail.detail ?? "");
    // A THIRD shape: FastAPI's own `HTTPException(detail="some string")`, which the
    // taxonomy does not wrap. `/auth/callback` uses it for an unprovisioned identity
    // (ADR-011), where the message is deliberately specific — "Ask an administrator"
    // is the only instruction that path can give. Without this branch it fell through
    // to the generic case below and the user was told "Forbidden", which is true and
    // useless. Reported as the client half of #111 C-1.
    if (typeof body?.detail === "string" && body.detail) {
      return new ApiError(response.status, "http_error", body.detail);
    }
  } catch {
    /* fall through to the generic shape */
  }
  return new ApiError(response.status, "http_error", response.statusText || `HTTP ${response.status}`);
}

/**
 * `GET` a JSON resource.
 *
 * `credentials: "same-origin"` is explicit rather than relied upon: the session is an
 * httpOnly cookie, and a request that silently omitted it would read as logged-out
 * rather than as misconfigured.
 */
export async function apiGet<T>(path: string, params?: Params): Promise<T> {
  const response = await fetch(`${API_BASE}${path}${query(params)}`, {
    method: "GET",
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });

  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as T;
}

/**
 * `GET` a resource that may legitimately not exist.
 *
 * Returns `null` on 404 and throws on everything else. The mock APIs returned `null`
 * for a missing id, and preserving that keeps every calling surface unchanged — a
 * missing resource is a state those surfaces already render, while a 403 is not.
 */
export async function apiGetOrNull<T>(path: string, params?: Params): Promise<T | null> {
  try {
    return await apiGet<T>(path, params);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

/**
 * Send a JSON body and read a JSON response.
 *
 * One function behind `apiPost`/`apiPatch` rather than three near-copies, because the
 * part worth getting right — credentials, the error envelope, the 204 case — is
 * identical and should not drift between verbs.
 */
async function send<T>(method: string, path: string, body?: unknown, params?: Params): Promise<T> {
  const response = await fetch(`${API_BASE}${path}${query(params)}`, {
    method,
    credentials: "same-origin",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (!response.ok) throw await toApiError(response);

  // 204 has no body, and `response.json()` on an empty body throws a parse error that
  // would surface as a crash on a successful delete.
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** `POST` a JSON body. Creates return 201; action endpoints return 200. */
export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return send<T>("POST", path, body);
}

/**
 * `PATCH` a JSON body.
 *
 * **Only send the fields the user actually changed.** The API distinguishes an omitted
 * field from an explicit `null`: omitted leaves the value alone, `null` clears it. A
 * caller that serialises its whole form state will send `null` for every empty input
 * and silently wipe fields nobody touched.
 */
export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return send<T>("PATCH", path, body);
}

/**
 * `DELETE`, with the concurrency check in the query string.
 *
 * `expected_version` is required by the API and travels as a parameter rather than a
 * body, because a request body on DELETE is legal but poorly supported by proxies.
 */
export async function apiDelete(path: string, expectedVersion: number): Promise<void> {
  await send<void>("DELETE", path, undefined, { expected_version: String(expectedVersion) });
}
