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

from fastapi import APIRouter, Response, status
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


@router.post(
    "/api/membership",
    status_code=status.HTTP_200_OK,
    # Declared explicitly so the 202 is in the schema and not only in the code. Without
    # this entry the spec shows one success response, and a generated client has no reason
    # to handle the pending case at all — the contract would live in a docstring.
    responses={
        status.HTTP_202_ACCEPTED: {
            "model": domain.MembershipRequest,
            "description": "Filed for approval; no membership was written.",
        }
    },
)
def grant_membership(
    payload: MembershipGrant, principal: CurrentPrincipal, response: Response
) -> domain.Membership | domain.MembershipRequest:
    """Grants a membership, or files one for approval — **200 vs 202** (#225).

    The target workspace is `principal.workspace_id` — the session's own selection
    — never a value from `payload`. Anti-escalation (`domain.grant_membership`)
    refuses a role above the caller's own clearance before any write is attempted.

    **200** means the membership is live, and the body is unchanged from before #225 —
    a founder's or admin's grant takes effect immediately and every existing client
    keeps working. **202 Accepted** means the caller is not an approver: the body is the
    pending `MembershipRequest`, and nothing has been written to `membership`.

    The distinction is carried by the status code because that is the one field a client
    cannot read past by accident. A shared 200 with a `status` field to inspect would let
    a client that never added the check report a pending request as a completed grant —
    which is precisely the false confirmation the approval requirement must not produce.
    """
    outcome = domain.grant_membership(
        str(payload.principal_id),
        payload.role,
        workspace_id=principal.workspace_id,
        actor_principal_id=str(principal.id),
    )
    if isinstance(outcome, domain.MembershipRequest):
        response.status_code = status.HTTP_202_ACCEPTED
    return outcome


@router.get("/api/membership/requests")
def list_membership_requests(principal: CurrentPrincipal) -> list[domain.MembershipRequest]:
    """The pending approval queue for the caller's workspace. Founders and admins only.

    Registered BEFORE `/api/membership/{principal_id}/revoke` is irrelevant to matching —
    that route is a POST with a different arity — but the literal `requests` segment is
    load-bearing for a different reason: the approve/reject routes below live under it, so
    the queue and its actions share one prefix instead of competing with `{principal_id}`
    for the same position.
    """
    return domain.list_pending_requests(
        workspace_id=principal.workspace_id,
        actor_principal_id=str(principal.id),
    )


@router.post("/api/membership/requests/{request_id}/approve")
def approve_membership_request(
    request_id: uuid.UUID, principal: CurrentPrincipal
) -> domain.Membership:
    """Signs a pending request. Returns the membership that is now in effect.

    Returns a `Membership`, not the decided request: the caller's question is "does this
    person have access now", and answering with the request row would make them fetch
    again to find out.
    """
    return domain.approve_membership_request(
        str(request_id),
        workspace_id=principal.workspace_id,
        actor_principal_id=str(principal.id),
    )


@router.post("/api/membership/requests/{request_id}/reject")
def reject_membership_request(
    request_id: uuid.UUID, principal: CurrentPrincipal
) -> domain.MembershipRequest:
    """Refuses a pending request. Nothing is written to `membership`."""
    return domain.reject_membership_request(
        str(request_id),
        workspace_id=principal.workspace_id,
        actor_principal_id=str(principal.id),
    )


@router.post("/api/membership/{principal_id}/revoke")
def revoke_membership(principal_id: uuid.UUID, principal: CurrentPrincipal) -> domain.Membership:
    """Revokes a membership (`active = false`) in the caller's workspace."""
    return domain.revoke_membership(
        str(principal_id),
        workspace_id=principal.workspace_id,
        actor_principal_id=str(principal.id),
    )
