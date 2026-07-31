"""Read endpoints for meeting minutes (Meridian P3, CP-C — ADR-014).

1:1 with `meridian/minutes.py`, minus `workspace_id` (ADR-013).

**No clearance parameter, and that is the contract rather than an omission.** The
`minutes` table has no `sensitivity` column and no function in the domain accepts a
clearance — minutes are workspace-scoped only. Whether they *should* be filtered is a
real open question (issue #49); adding a parameter the domain cannot honour would
answer it by accident.

`meeting_id` is required, mirroring `list_minutes`. The frontend mock made it optional
and added a `status` filter the domain has never had. Minutes belong to a meeting, and
a workspace-wide list of every version of every meeting's minutes is not a question the
domain was built to answer.
"""

import uuid

from fastapi import APIRouter

from meridian import minutes as domain
from meridian.api.deps import CurrentPrincipal

router = APIRouter(prefix="/api/minutes", tags=["minutes"])


@router.get("")
def list_minutes(meeting_id: uuid.UUID, principal: CurrentPrincipal) -> list[domain.Minutes]:
    """Every minutes version for a meeting, `version_no DESC, created_at DESC`.

    Returns all versions, not just the standing one: the correction trail is the
    point of this surface, and a list that showed only the current record would hide
    exactly what a board needs to reconstruct.
    """
    return domain.list_minutes(str(meeting_id), workspace_id=principal.workspace_id)


@router.get("/{minutes_id}")
def get_minutes(minutes_id: uuid.UUID, principal: CurrentPrincipal) -> domain.Minutes:
    return domain.get_minutes(str(minutes_id), workspace_id=principal.workspace_id)
