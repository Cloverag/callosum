"""Workspace bootstrap and membership administration endpoints (#166 step 5).

`POST /workspaces` — plural, so it does not collide with `POST /auth/workspace`
(A4's *selection* endpoint) — is the one route in this API that does NOT depend on
`CurrentPrincipal`. It cannot: `current_principal()` resolves a `Principal` by
joining `principal` to an ACTIVE membership in a chosen workspace, and a caller
creating their first workspace has neither yet. It depends on `CurrentSession`
instead — identity only, no authorization — and that is the whole reason this
route is allowed to exist at all outside the membership-gated rest of the API.

Every other route here — grant, change, revoke — takes its target workspace from
`CurrentWorkspace`/`CurrentPrincipal` (the session), never from the request body,
per ADR-013 and the maintainer's ruling on #166 step 5.
"""

import uuid

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict

from meridian import workspaces as domain
from meridian.api.deps import CurrentPrincipal, CurrentSession

router = APIRouter(tags=["workspaces"])


class WorkspaceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    external_id: str | None = None


class WorkspaceCreated(BaseModel):
    workspace_id: str


class MembershipGrant(BaseModel):
    """No `workspace_id` field, deliberately — see the module docstring."""

    model_config = ConfigDict(extra="forbid")

    principal_id: uuid.UUID
    role: str


@router.post("/workspaces", status_code=status.HTTP_201_CREATED)
def create_workspace(payload: WorkspaceCreate, session: CurrentSession) -> WorkspaceCreated:
    """Creates a workspace with the caller as its founder.

    `CurrentSession`, not `CurrentPrincipal`: the caller has no membership anywhere
    yet, by construction — that is exactly the gap this route exists to close, and
    depending on `CurrentPrincipal` here would make the route unable to serve the
    one caller it exists for.
    """
    workspace_id = domain.create_workspace(
        payload.name, payload.external_id, session.principal_id
    )
    return WorkspaceCreated(workspace_id=workspace_id)


@router.post("/api/membership", status_code=status.HTTP_200_OK)
def grant_membership(payload: MembershipGrant, principal: CurrentPrincipal) -> domain.Membership:
    """Grants a new membership, or changes an existing one's role, in the caller's workspace.

    The target workspace is `principal.workspace_id` — the session's own selection
    — never a value from `payload`. Anti-escalation (`domain.grant_membership`)
    refuses a role above the caller's own clearance before any write is attempted.
    """
    return domain.grant_membership(
        str(payload.principal_id),
        payload.role,
        workspace_id=principal.workspace_id,
        actor_principal_id=str(principal.id),
        actor_clearance=principal.clearance,
    )


@router.post("/api/membership/{principal_id}/revoke")
def revoke_membership(principal_id: uuid.UUID, principal: CurrentPrincipal) -> domain.Membership:
    """Revokes a membership (`active = false`) in the caller's workspace."""
    return domain.revoke_membership(
        str(principal_id),
        workspace_id=principal.workspace_id,
        actor_principal_id=str(principal.id),
        actor_clearance=principal.clearance,
    )
