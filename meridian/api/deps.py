"""Per-request authorization, derived and never cached (P3, CP-A/A4 — ADR-012).

This module is the only place a request acquires a `Principal`, and it rebuilds one
from the database on **every** call.

---------------------------------------------------------------------------
WHY RE-RESOLVE INSTEAD OF CACHING
---------------------------------------------------------------------------
The session carries `principal_id` and a chosen `workspace_id` — an identity and a
selection. It carries no clearance, no role and no membership, because those are
authorization facts and authorization facts get revoked.

The cost of caching is not hypothetical. The same principal can hold *different*
clearances in different workspaces — verified: clearance 1 in one, 4 in another. A
clearance copied into a cookie is therefore wrong the moment the workspace changes,
and stale the moment a membership does. Re-resolving costs one indexed JOIN and makes
revocation take effect on the next request rather than at session expiry.

---------------------------------------------------------------------------
VERIFY, DO NOT ENUMERATE
---------------------------------------------------------------------------
There is deliberately no "list my workspaces" endpoint, and it is not an omission.
`membership` and `workspace` are both RLS-scoped to `app.workspace_id`, so the runtime
role can see exactly one workspace at a time — enumeration is impossible by
construction, which is a P1 property worth keeping rather than working around.

Selection therefore names a workspace and this module verifies membership in it. A
caller who names one they do not belong to is refused, and learns nothing about
whether it exists.
"""

import os
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from callosum import store
from callosum.identity import PrincipalNotFound, resolve_principal_by_id
from callosum.retrieve import Principal
from meridian.api import session as sess
from meridian.api.session import AuthenticatedSession
from meridian.tenancy import WorkspaceRequired, require_workspace

#: Machine-readable codes, so a client can tell "log in" from "pick a workspace"
#: without parsing prose. Both are 4xx and only one of them means re-authenticate.
NOT_AUTHENTICATED = "not_authenticated"
SESSION_NOT_CONFIGURED = "session_not_configured"
WORKSPACE_NOT_SELECTED = "workspace_not_selected"
FORBIDDEN = "forbidden"


#: Environments in which the development auto-login affordance may run at all.
#:
#: An **allowlist**. The previous check was `env != "production"`, which is a denylist
#: of exactly one string, and a denylist of one string is fail-open three ways: the
#: variable being unset, the variable being empty, and the variable being misspelled
#: (`prod`, `PRODUCTION `, `production-eu`) all landed on the permissive side. An
#: allowlist inverts every one of those — anything unrecognised means "not a
#: development machine", which is the assumption that is safe to be wrong about.
DEV_AUTH_ENVIRONMENTS = frozenset({"development", "test", "local"})

#: Accepted truthy spellings for `MERIDIAN_DEV_AUTO_AUTH`. Unchanged from the original.
_DEV_AUTH_TRUTHY = frozenset({"true", "1", "yes"})


def _dev_auto_auth_enabled() -> bool:
    """Whether the development auto-login affordance may run. **Fail-closed.**

    Auto-login fabricates an `AuthenticatedSession` for a request that presented no
    session at all, choosing `ORDER BY p.created_at ASC LIMIT 1` — the *first* seeded
    principal, which under `cli.DEMO_PRINCIPALS` is the founder at clearance 4. It is
    therefore not merely an authentication bypass but one that lands on the highest
    privilege in the system, and it must be off unless someone has said twice that
    they want it.

    Two independent conditions, both required:

      1. The environment is *explicitly* one of `DEV_AUTH_ENVIRONMENTS`. Unset,
         empty, unrecognised or production all mean off. This is the half that
         changed: the default used to be `"development"`, so an unset variable
         satisfied the check and a deployment that simply forgot to set it was one
         env var away from anonymous founder access.
      2. `MERIDIAN_DEV_AUTO_AUTH` is explicitly truthy.

    Production safety must not depend on a deployment's compose file remembering to
    pin `ENVIRONMENT=production`. It now depends on nothing being set, which is the
    state every fresh environment starts in.

    `ENVIRONMENT` takes precedence over `APP_ENV`, and an empty `ENVIRONMENT` falls
    through to `APP_ENV` rather than short-circuiting to a value — `os.environ.get`
    with a default returns `""` for a variable set to empty, so the original
    `get("ENVIRONMENT", get("APP_ENV", ...))` never consulted `APP_ENV` once
    `ENVIRONMENT=` appeared in a `.env` file. Both spellings reach the same
    allowlist here, and neither can widen it.
    """
    env = (os.environ.get("ENVIRONMENT") or os.environ.get("APP_ENV") or "").strip().lower()
    if env not in DEV_AUTH_ENVIRONMENTS:
        return False
    return os.environ.get("MERIDIAN_DEV_AUTO_AUTH", "").strip().lower() in _DEV_AUTH_TRUTHY


def current_session(request: Request) -> AuthenticatedSession:
    """The authenticated identity, or 401.

    Identity only — this says who the caller claims to be and nothing about what they
    may do. A partial session reads as absent (see `session.read`), so a malformed
    cookie is a logged-out request rather than a half-trusted one.
    """
    try:
        raw = request.session
    except AssertionError as exc:
        # `SessionMiddleware` is installed only when a signing secret is configured
        # (see `api/main.py`) — deliberately, because handing out forgeable cookies is
        # worse than refusing to start the feature. But the resulting failure was an
        # `AssertionError` on every authenticated request, i.e. a 500: an internal
        # error, for a configuration problem the operator can fix in one line.
        #
        # `main.py` already treats missing OIDC config this way — "the routes still
        # mount and answer 503, which is a deployment state, not a crash". This gives
        # the session path the same treatment.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": SESSION_NOT_CONFIGURED,
                "detail": "Sessions are not configured on this server; set MERIDIAN_SESSION_SECRET.",
            },
        ) from exc

    current = sess.read(raw)
    if current is None:
        if _dev_auto_auth_enabled():
            with store.pg(store.DEFAULT_WORKSPACE_ID) as conn:
                row = conn.execute(
                    """
                    SELECT p.id, pi.provider, pi.subject
                      FROM principal p
                      JOIN membership m ON m.principal_id = p.id
                 LEFT JOIN principal_identity pi ON pi.principal_id = p.id
                     WHERE m.workspace_id = %s AND m.active
                     ORDER BY p.created_at ASC
                     LIMIT 1
                    """,
                    (store.DEFAULT_WORKSPACE_ID,),
                ).fetchone()
                if row:
                    return AuthenticatedSession(
                        principal_id=str(row["id"]),
                        provider=row["provider"] or "http://localhost:8080/realms/meridian",
                        subject=row["subject"] or "raj@callosum.inc",
                        workspace_id=store.DEFAULT_WORKSPACE_ID,
                    )
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"code": NOT_AUTHENTICATED, "detail": "Not authenticated."},
        )
    return current


def current_workspace(
    current: Annotated[AuthenticatedSession, Depends(current_session)],
) -> str:
    """The selected workspace id, validated as well-formed, or 409.

    409 rather than 401: the caller *is* authenticated, they simply have not chosen a
    workspace yet. Telling them to log in again would be wrong and would loop.

    Validation goes through `meridian.tenancy.require_workspace()` — the guard that
    raises instead of letting a missing value reach `store.pg()`, where it would
    silently become the Default Workspace.
    """
    if current.workspace_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": WORKSPACE_NOT_SELECTED,
                "detail": "No workspace selected for this session.",
            },
        )

    try:
        return require_workspace(current.workspace_id)
    except WorkspaceRequired as exc:
        # A session carrying an unparseable workspace is not a request to repair — it
        # is something unexpected, and treating it as "no selection" is the closed
        # answer rather than the convenient one.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": WORKSPACE_NOT_SELECTED, "detail": str(exc)},
        ) from exc


def current_principal(
    current: Annotated[AuthenticatedSession, Depends(current_session)],
    workspace_id: Annotated[str, Depends(current_workspace)],
) -> Principal:
    """The caller's live authorization context. **Every endpoint should depend on this.**

    Rebuilds a `Principal` — including clearance — from the database on every request,
    using only the identity and selection the session carries.

    Fail-closed: `resolve_principal_by_id()` JOINs `principal` to an *active*
    membership in this workspace, so a revoked or deactivated membership stops
    resolving immediately. No logout is required and no cache needs invalidating,
    because nothing was cached.

    The 403 is deliberately uniform. "You were never a member", "your membership was
    revoked" and "that workspace is not yours" are one answer, matching
    `PrincipalNotFound`'s own conflation — distinguishing them would confirm which
    workspaces exist to someone who cannot see them.
    """
    with store.pg(workspace_id) as conn:
        try:
            return resolve_principal_by_id(
                conn, current.principal_id, workspace_id=workspace_id
            )
        except PrincipalNotFound as exc:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail={"code": FORBIDDEN, "detail": "Not available to you."},
            ) from exc


def verify_membership(principal_id: str, workspace_id: str) -> Principal:
    """Checks a principal into a workspace, for the selection step.

    Reuses `resolve_principal_by_id()` rather than asking `membership` a second
    question of its own — there is one membership rule in this system and adding a
    parallel check here is how the two would drift apart.

    Raises `PrincipalNotFound` on failure; the caller maps it to a response.
    """
    validated = require_workspace(workspace_id)
    with store.pg(validated) as conn:
        return resolve_principal_by_id(conn, principal_id, workspace_id=validated)


#: Annotated aliases, so endpoints read as `principal: CurrentPrincipal` rather than
#: repeating the Depends() wiring — and so A5's schema test sees one consistent shape.
CurrentSession = Annotated[AuthenticatedSession, Depends(current_session)]
CurrentWorkspace = Annotated[str, Depends(current_workspace)]
CurrentPrincipal = Annotated[Principal, Depends(current_principal)]
