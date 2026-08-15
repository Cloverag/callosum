"""Meeting Preparation API endpoints (Meridian P3, CP-B/E).

Exposes readiness evaluation, derived agenda suggestions, and pre-read publication.

---------------------------------------------------------------------------
EVERY HANDLER HERE DEPENDS ON `CurrentPrincipal`, AND THAT IS THE POINT
---------------------------------------------------------------------------
These three endpoints previously took `current_session` + `current_workspace`.
Neither checks membership: `current_session` says who the caller claims to be, and
`current_workspace` only validates that the id in the cookie is a well-formed UUID.
The membership check lives in `current_principal`, which JOINs to an **active**
membership through `resolve_principal_by_id()`.

The consequence was that a principal whose membership had been revoked kept working
here until their session expired — up to 24 hours — including on `publish-preread`,
which publishes a board pack. `deps.py` states the rule this file was not following:

    Rebuilds a `Principal` — including clearance — from the database on every
    request... a revoked or deactivated membership stops resolving immediately.

There is no clearance filter in this module and that is not an omission: `prep` reads
`decision`, `commitment` and `board_member`, none of which carry a `sensitivity`
column, and the `board_pack` header rather than its items — pack *items* take
clearance from a JOIN to `document.sensitivity` (see `packs.py`) and are never read
here. If this module ever grows a query over `board_pack_item`, it needs
`principal.clearance` alongside the membership check, not instead of it.
"""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from meridian import prep
from meridian.api import deps

router = APIRouter(prefix="/api/meetings/{meeting_id}", tags=["prep"])


class PrepSourceModel(BaseModel):
    kind: str
    id: str
    label: str


class AgendaSuggestionResponse(BaseModel):
    title: str
    reason: str
    source: PrepSourceModel
    suggested_duration_minutes: int


class ReadinessResponse(BaseModel):
    meeting_id: str
    meeting_title: str
    status: str
    scheduled_start: str | None = None
    agenda_count: int
    has_published_pack: bool
    pack_version: int | None = None
    open_decisions_count: int
    overdue_commitments_count: int
    attendee_count: int


class PublishPrereadResponse(BaseModel):
    meeting_id: str
    pack_id: str
    version_no: int
    status: str


@router.get("/readiness", response_model=ReadinessResponse)
def get_readiness(
    meeting_id: uuid.UUID,
    principal: deps.CurrentPrincipal,
) -> dict[str, Any]:
    """Get meeting readiness metrics."""
    try:
        return prep.get_meeting_readiness(meeting_id, workspace_id=principal.workspace_id)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/agenda-suggestions", response_model=list[AgendaSuggestionResponse])
def get_agenda_suggestions(
    meeting_id: uuid.UUID,
    principal: deps.CurrentPrincipal,
) -> list[dict[str, Any]]:
    """Get derived agenda item suggestions for the meeting."""
    try:
        return prep.get_agenda_suggestions(meeting_id, workspace_id=principal.workspace_id)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/publish-preread", response_model=PublishPrereadResponse)
def publish_preread(
    meeting_id: uuid.UUID,
    principal: deps.CurrentPrincipal,
) -> dict[str, Any]:
    """Publish the board pack as a permissioned pre-read.

    The write on this router, and so the one where a stale membership mattered most:
    publishing is a state change attributed to the actor in the audit trail.
    """
    try:
        return prep.publish_preread(
            meeting_id,
            workspace_id=principal.workspace_id,
            actor_id=str(principal.id),
        )
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
