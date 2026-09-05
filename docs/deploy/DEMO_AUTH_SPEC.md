# Demo principal selector — specification, not implementation

Backend work. Belongs to the existing backend ownership alongside the auto-auth fix,
for the same reason: it touches the identity boundary, and a demo-shaped workaround
living outside that boundary is how a parallel authorization path gets built.

## The constraint

> The selector must still enter the existing Callosum identity/authorization path.
> Do not create a parallel authorization implementation.

What OIDC actually provides is one thing: an **identity assertion** — "this browser
belongs to subject X". Everything after that is already Meridian's, and none of it may
be duplicated:

    identity assertion  <- Keycloak provides this; the selector replaces ONLY this
    -----------------------------------------------------------------------------
    session write       <- meridian/api/session.py, unchanged
    principal resolve   <- identity.resolve_principal_by_id, unchanged
    workspace verify    <- deps.current_workspace, unchanged
    clearance derive    <- membership.role -> ROLE_TO_CLEARANCE, unchanged
    RLS scoping         <- store.pg(workspace_id), unchanged
    row filtering       <- d.sensitivity <= clearance, in SQL, unchanged

So the selector is a route that writes a session and returns. It must not construct a
`Principal`, must not read `principal.role` or `principal.clearance`, and must not pass
a clearance to anything.

## Shape

`POST /auth/demo/select` with `{"principal_id": "<uuid>"}`:

1. Refuse unless the demo selector is explicitly enabled — same fail-closed shape as
   `_dev_auto_auth_enabled()`: an allowlisted environment **and** an explicit flag,
   both required, unset means off. Reuse that helper's pattern; do not invent a
   second convention.
2. Resolve via `identity.resolve_principal_by_id(conn, principal_id,
   workspace_id=DEFAULT_WORKSPACE_ID)`. This is the fail-closed JOIN — an id with no
   active membership raises `PrincipalNotFound` and the route returns the same
   uniform 403 `current_principal` already returns. No special-casing.
3. Write the session with `meridian.api.session`, exactly as the OIDC callback does.
4. Return 204. Return no clearance, no role, no membership — the client learns who it
   is on the next request like every other client.

`GET /auth/demo/principals` lists selectable principals (id + name only) so the UI has
something to render. **Names and ids only** — publishing roles or clearances beside them
turns the selector into a directory of who can see what.

## Why this is not the auto-auth bypass again

The bypass fabricated a session for a request that asked for nothing, and chose the
highest-privilege principal by `created_at`. This requires an explicit id from an
explicit request, is off by default under the same two-condition guard, and grants
nothing the caller's membership does not already carry.

It is still an authentication bypass in the literal sense — anyone who can reach the
route can become any listed principal. That is acceptable **only** because the demo
database contains fabricated board minutes and nothing else. It must never ship
enabled against real data, and the flag name should say so.

## Label, verbatim, on the page

    Demo auth — pick a principal. Production uses Keycloak OIDC.

## Estimated size

One route module (~60 lines with the docstring density of this codebase), one
`main.py` registration guarded by the same flag, and tests: enabled/disabled by
environment, unknown id -> 403, revoked membership -> 403, and the mutation that
matters — a principal id with no membership must not produce a session.
