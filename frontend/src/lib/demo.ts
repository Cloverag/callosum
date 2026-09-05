/**
 * The demo principal selector — client for `meridian/api/demo.py`.
 *
 * The browser sends a SYMBOL, never a principal id. `identity` is typed as a union of
 * three literals here and as a `Literal` on the server, so an id cannot be smuggled
 * through this path even if this file were edited: the server rejects anything outside
 * the enum with 422 before its handler runs.
 *
 * Nothing here derives, caches or computes an authorization fact. Selecting an identity
 * writes a session; every number on screen afterwards comes from the API response.
 */

import { authFetch } from "@/lib/auth";

/** Mirrors `DemoIdentity` in `meridian/api/demo.py`. */
export type DemoIdentity = "founder" | "exec" | "investor";

export type DemoIdentityOption = {
  symbol: DemoIdentity;
  /** Display text only. The server deliberately sends no role and no clearance. */
  label: string;
};

/**
 * Available demo identities, or `null` when the selector is disabled.
 *
 * A disabled selector answers 404 — deliberately indistinguishable from "no such
 * route", so a real deployment does not advertise an impersonation endpoint. The page
 * treats `null` as "this build is not a demo" rather than as an error.
 */
export async function listDemoIdentities(): Promise<DemoIdentityOption[] | null> {
  try {
    const body = await authFetch<{ identities: DemoIdentityOption[] }>("/demo/identities");
    return body.identities;
  } catch {
    return null;
  }
}

/**
 * Establishes a session for one seeded demo principal.
 *
 * `/auth/demo/*`, not `/api/...`: the auth routes are mounted at `/auth` and Next
 * proxies that as a separate prefix, so these go through `authFetch`. Using `apiGet`
 * here would request `/api/auth/demo/...`, which does not exist.
 *
 * The response echoes the symbol and the provider marker only — no role and no
 * clearance. What this identity may see is learned by making the next request.
 */
export async function selectDemoIdentity(identity: DemoIdentity): Promise<void> {
  await authFetch<{ identity: string; provider: string }>("/demo/select", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ identity }),
  });
}
