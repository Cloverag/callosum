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

  /** True when the session needs re-establishing rather than the request retrying. */
  get isUnauthenticated(): boolean {
    return this.status === 401;
  }

  /** True when authenticated but no workspace has been chosen yet. */
  get needsWorkspace(): boolean {
    return this.status === 409 && this.code === "workspace_not_selected";
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

async function toApiError(response: Response): Promise<ApiError> {
  // The taxonomy returns {"error": {"code", "detail"}}. Anything else — a proxy error
  // page, a gateway timeout — is still surfaced as an ApiError rather than as a parse
  // failure, because a caller handling errors should not also have to handle the
  // error handler failing.
  try {
    const body = await response.json();
    const error = body?.error;
    if (error?.code) return new ApiError(response.status, error.code, error.detail ?? response.statusText);
    if (body?.detail?.code) return new ApiError(response.status, body.detail.code, body.detail.detail ?? "");
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
