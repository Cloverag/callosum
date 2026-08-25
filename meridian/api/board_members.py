"""Board directory endpoints (Meridian P3, CP-C reads · CP-D writes — ADR-014).

1:1 with `meridian/board_members.py`, minus `workspace_id`, which comes from the
session (ADR-013).

`list_members` takes `active: bool | None = True` — a **tri-state**: active only by
default, `False` for departed members only, `None` for everyone. HTTP has no natural
way to distinguish "parameter omitted" from "explicitly no filter" on a boolean, so
the wire spells the third state out as `all`. Collapsing it to a two-valued
`include_inactive` is what the frontend mock did, and it silently dropped the
inactive-only case.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict

from meridian import board_members as domain
from meridian.api.deps import CurrentPrincipal


class MemberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str
    role: str
    #: Optional link to a `principal`. A director who has no account is still a
    #: director — the directory records the board, not the user list.
    principal_id: uuid.UUID | None = None
    organization: str | None = None
    contact_email: str | None = None
    voting: str = "voting"


class MemberPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int
    full_name: str | None = None
    organization: str | None = None
    role: str | None = None
    contact_email: str | None = None
    voting: str | None = None


class MemberVersioned(BaseModel):
    """For deactivate/reactivate — the whole body is the concurrency check."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int

router = APIRouter(prefix="/api/board-members", tags=["board-members"])

#: Wire spelling of the domain's tri-state, and the mapping back to it.
_ACTIVE: dict[str, bool | None] = {"true": True, "false": False, "all": None}


@router.get("")
def list_members(
    principal: CurrentPrincipal,
    active: Literal["true", "false", "all"] = "true",
    role: str | None = None,
) -> list[domain.BoardMember]:
    """The directory, active members only unless asked otherwise.

    `active=true` is the default because the directory's everyday use is "who is on
    the board now". `all` is what a surface rendering *history* needs — a departed
    director still cast the votes on record, and filtering them out would make those
    votes render as unresolvable, which reads as data loss rather than a departure.
    """
    return domain.list_members(
        workspace_id=principal.workspace_id,
        active=_ACTIVE[active],
        role=role,
    )


@router.get("/{member_id}")
def get_member(member_id: uuid.UUID, principal: CurrentPrincipal) -> domain.BoardMember:
    """One member, active or not.

    Deliberately returns inactive members, mirroring the domain: historical stances
    and votes resolve through this, and a departed director must not become
    unresolvable.
    """
    return domain.get_member(str(member_id), workspace_id=principal.workspace_id)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_member(payload: MemberCreate, principal: CurrentPrincipal) -> domain.BoardMember:
    """Adds a director to the workspace directory.

    Deliberately no uniqueness on `(workspace_id, full_name)`: two real people can share
    a name, and this system's alias machinery exists precisely because names collide.
    """
    return domain.create_member(
        payload.full_name,
        payload.role,
        workspace_id=principal.workspace_id,
        principal_id=str(payload.principal_id) if payload.principal_id else None,
        organization=payload.organization,
        contact_email=payload.contact_email,
        voting=payload.voting,
        actor_principal_id=str(principal.id) if principal.id else None,
    )


@router.patch("/{member_id}")
def update_member(
    member_id: uuid.UUID, payload: MemberPatch, principal: CurrentPrincipal
) -> domain.BoardMember:
    """Edits a directory entry under optimistic concurrency.

    `active` is not patchable — leaving the board is `deactivate`, which is a distinct
    event rather than a field edit.
    """
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("expected_version", None)
    return domain.update_member(
        str(member_id),
        expected_version=payload.expected_version,
        workspace_id=principal.workspace_id,
        actor_principal_id=str(principal.id) if principal.id else None,
        **changes,
    )


@router.post("/{member_id}/deactivate")
def deactivate_member(
    member_id: uuid.UUID, payload: MemberVersioned, principal: CurrentPrincipal
) -> domain.BoardMember:
    """Marks a director as departed. **Not a delete.**

    Their stances, votes and commitments reference them and remain valid — a decision
    taken by the board that existed at the time is not unmade by someone leaving. The
    composite `(id, workspace_id)` foreign keys make removal impossible anyway, which is
    the constraint enforcing the intent rather than a convention describing it.
    """
    return domain.deactivate_member(
        str(member_id),
        expected_version=payload.expected_version,
        workspace_id=principal.workspace_id,
        actor_principal_id=str(principal.id) if principal.id else None,
    )


@router.post("/{member_id}/reactivate")
def reactivate_member(
    member_id: uuid.UUID, payload: MemberVersioned, principal: CurrentPrincipal
) -> domain.BoardMember:
    """Returns a director to active service.

    Separate from `deactivate` rather than one toggle taking a boolean, per ADR-014's
    1:1 rule — and because the two are not symmetric operations to audit.
    """
    return domain.reactivate_member(
        str(member_id),
        expected_version=payload.expected_version,
        workspace_id=principal.workspace_id,
        actor_principal_id=str(principal.id) if principal.id else None,
    )
