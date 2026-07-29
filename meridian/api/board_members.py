"""Read endpoints for the board directory (Meridian P3, CP-C — ADR-014).

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

from fastapi import APIRouter

from meridian import board_members as domain
from meridian.api.deps import CurrentPrincipal

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
