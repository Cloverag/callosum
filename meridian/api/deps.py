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
WORKSPACE_NOT_SELECTED = "workspace_not_selected"
FORBIDDEN = "forbidden"


def current_session(request: Request) -> AuthenticatedSession:
    """The authenticated identity, or 401.

    Identity only — this says who the caller claims to be and nothing about what they
    may do. A partial session reads as absent (see `session.read`), so a malformed
    cookie is a logged-out request rather than a half-trusted one.
    """
    current = sess.read(request.session)
    if current is None:
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
