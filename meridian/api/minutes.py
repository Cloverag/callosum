"""Meeting minutes endpoints (Meridian P3, CP-C reads · CP-D writes — ADR-014).

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
from pydantic import BaseModel, ConfigDict

from meridian import minutes as domain
from meridian.api.deps import CurrentPrincipal


class MinutesCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meeting_id: uuid.UUID
    #: The minutes text. Named `body` in the domain and kept `body` here — renaming it
    #: at the boundary would be one more thing to remember in both directions.
    body: str


class MinutesPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int
    body: str | None = None


class MinutesVersioned(BaseModel):
    """For `finalise` — the whole body is the concurrency check."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int


class MinutesSupersede(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_body: str
    expected_version: int


class MinutesSupersession(BaseModel):
    """Both halves — the caller needs each."""

    superseded: domain.Minutes
    replacement: domain.Minutes

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


@router.post("", status_code=201)
def create_minutes(payload: MinutesCreate, principal: CurrentPrincipal) -> domain.Minutes:
    """Starts draft minutes for a meeting.

    The domain refuses minutes on a `draft` meeting — there is nothing to minute until
    a meeting has at least been scheduled.
    """
    return domain.create_minutes(
        str(payload.meeting_id), payload.body, workspace_id=principal.workspace_id
    )


@router.patch("/{minutes_id}")
def update_minutes(
    minutes_id: uuid.UUID, payload: MinutesPatch, principal: CurrentPrincipal
) -> domain.Minutes:
    """Edits draft minutes under optimistic concurrency.

    `body` is `NOT NULL`, so a `null` is refused here rather than travelling to the
    domain to be refused there.
    """
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("expected_version", None)
    return domain.update_minutes(
        str(minutes_id),
        expected_version=payload.expected_version,
        workspace_id=principal.workspace_id,
        **changes,
    )


@router.post("/{minutes_id}/finalise")
def finalise_minutes(
    minutes_id: uuid.UUID, payload: MinutesVersioned, principal: CurrentPrincipal
) -> domain.Minutes:
    """Freezes minutes as the record of a meeting.

    Final minutes are not editable. A correction is a new version through `supersede`,
    which is what keeps "what the board was told at the time" recoverable.
    """
    return domain.finalise_minutes(
        str(minutes_id),
        expected_version=payload.expected_version,
        workspace_id=principal.workspace_id,
    )


@router.post("/{minutes_id}/supersede", status_code=201)
def supersede_minutes(
    minutes_id: uuid.UUID, payload: MinutesSupersede, principal: CurrentPrincipal
) -> MinutesSupersession:
    """Issues corrected minutes, keeping the superseded version readable.

    The domain returns `(new, old)`, named here for the same reason as everywhere else.
    """
    new, old = domain.supersede_minutes(
        str(minutes_id),
        payload.new_body,
        expected_version=payload.expected_version,
        workspace_id=principal.workspace_id,
    )
    return MinutesSupersession(superseded=old, replacement=new)
