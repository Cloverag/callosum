# Demo principal selector — specification

Implemented on `master` by PR #199 (`meridian/api/demo.py`). This file is the contract
that implementation must keep matching. It is **not** a design sketch for a UUID
impersonation endpoint — that shape was rejected before merge.

## The constraint

> The selector must still enter the existing Callosum identity/authorization path.
> Do not create a parallel authorization implementation.

What OIDC actually provides is one thing: an **identity assertion** — "this browser
belongs to subject X". Everything after that is already Meridian's, and none of it may
be duplicated:

    identity assertion  <- Keycloak provides this; the selector replaces ONLY this
    -----------------------------------------------------------------------------
    session write       <- meridian.api.session, unchanged
    principal resolve   <- identity.resolve_principal_by_id, unchanged
    workspace verify    <- deps.current_workspace, unchanged
    clearance derive    <- membership.role -> ROLE_TO_CLEARANCE, unchanged
    RLS scoping         <- store.pg(workspace_id), unchanged
    row filtering       <- d.sensitivity <= clearance, in SQL, unchanged

So the selector is a route that writes a session and returns. It must not construct a
`Principal`, must not read `principal.role` or `principal.clearance`, and must not pass
a clearance to anything.

## Shape (as shipped)

The browser names a **symbol**, never a principal UUID.

- `POST /auth/demo/select` with `{"identity": "founder" | "exec" | "investor"}`.
  Anything else is 422 before the handler runs. Extra keys such as `principal_id` are
  ignored / forbidden; they must not become an identity.
- `GET /auth/demo/identities` lists `{symbol, label}` only. Labels carry no role and
  no clearance.
- **Off unless `MERIDIAN_DEMO_SELECTOR` is an explicit truthy value** (`true` / `1` /
  `yes`). Unset means 404, not 503 — a disabled impersonation route must not announce
  that it exists. This flag is independent of `_dev_auto_auth_enabled()` because the
  public demo pins `ENVIRONMENT=production`.
- Routes are mounted always, `include_in_schema=False`, so OpenAPI does not list them.
- The mapped email is looked up in `principal`; missing seed data is **503**, not 403.
  Store failures are 503. A principal with no active membership is the same uniform 403
  as every other path.
- Session write uses `provider="demo-selector"`. It must not pretend to be a Keycloak
  issuer.
- Production docs (`/docs`, `/openapi.json`) stay off when `ENVIRONMENT` is
  `production` unless `MERIDIAN_EXPOSE_DOCS` is set.

## Why this is not the auto-auth bypass again

The bypass fabricated a session for a request that asked for nothing, and chose the
highest-privilege principal by `created_at`. This requires an explicit symbol from an
explicit request, is off by default, and grants nothing the mapped membership does not
already carry.

It is still an authentication bypass in the literal sense — anyone who can reach the
route can become any listed identity. That is acceptable **only** because the demo
database contains fabricated board minutes and nothing else. It must never ship
enabled against real data. `callosum init` currently grants membership to **every**
`principal` row, not only the three it seeds — that is issue #201 and is a separate
defect on the same path.

## Label on the page

The signed-out screen offers the three demo identities when `GET /auth/demo/identities`
returns 200, and the ordinary OIDC "Sign in" button when that route 404s.
