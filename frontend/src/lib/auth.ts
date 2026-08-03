import { ApiError, toApiError } from "@/lib/http";

/**
 * The session endpoints.
 *
 * ---------------------------------------------------------------------------
 * WHY THIS DOES NOT USE `lib/http.ts`
 * ---------------------------------------------------------------------------
 * Every other client goes through `apiGet`/`apiPost`, whose base is `/api`. The auth
 * routes are mounted at `/auth`, which Next proxies as a separate prefix — so they are
 * a sibling of the API base, not a path beneath it. `toApiError` is shared rather than
 * reimplemented, because two parsers for one error envelope is how the two drift.
 */

/**
 * The caller's live authorization context.
 *
 * Mirrors `GET /auth/context` field for field. Every value is re-derived from the
 * database on the request — the session holds only a principal id and a workspace
 * choice — so this is the authorization state *now*, not as of sign-in.
 */
export type AuthContext = {
  principal_id: string;
  name: string;
  role: string;
  clearance: number;
  workspace_id: string;
};

async function authFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/auth${path}`, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      ...init,
    });
  } catch {
    // A network failure rejects with a TypeError, not an ApiError. Code 0 marks
    // "never reached the server", which is a different thing from any status the
    // server returned.
    throw new ApiError(0, "network", "Could not reach the server.");
  }

  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as T;
}

export const authApi = {
  /**
   * Who the caller is and where they are acting.
   *
   * Throws rather than returning null on failure, because the three failure modes need
   * different screens: 401 means sign in, 409 `workspace_not_selected` means choose a
   * workspace, anything else is a real error. Collapsing them to null would make the
   * gate guess.
   */
  context: () => authFetch<AuthContext>("/context"),

  /**
   * Chooses the workspace this session acts in (ADR-012).
   *
   * **This verifies, it does not enumerate.** `membership` and `workspace` are both
   * RLS-scoped to `app.workspace_id`, so the runtime role cannot list the workspaces a
   * principal belongs to — it can only be asked about one at a time. That is why the
   * caller supplies an id instead of picking from a menu: a menu would require an
   * endpoint that answers "which workspaces is this person in", which is the
   * membership oracle the design deliberately refuses.
   */
  selectWorkspace: (workspaceId: string) =>
    authFetch<unknown>("/workspace", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ workspace_id: workspaceId }),
    }),
};

/** Where the browser goes to start the OIDC flow. Not a fetch — a full navigation. */
export const LOGIN_URL = "/auth/login";
