"""Meeting Preparation API endpoints (Meridian P3, CP-B/E).

Exposes readiness evaluation, derived agenda suggestions, and pre-read publication.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from meridian import prep
from meridian.api import deps
from meridian.api.session import AuthenticatedSession

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
    request_session: Annotated[AuthenticatedSession, Depends(deps.current_session)],
    workspace_id: Annotated[str, Depends(deps.current_workspace)],
) -> dict[str, Any]:
    """Get meeting readiness metrics."""
    try:
        return prep.get_meeting_readiness(meeting_id, workspace_id=workspace_id)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/agenda-suggestions", response_model=list[AgendaSuggestionResponse])
def get_agenda_suggestions(
    meeting_id: uuid.UUID,
    request_session: Annotated[AuthenticatedSession, Depends(deps.current_session)],
    workspace_id: Annotated[str, Depends(deps.current_workspace)],
) -> list[dict[str, Any]]:
    """Get derived agenda item suggestions for the meeting."""
    try:
        return prep.get_agenda_suggestions(meeting_id, workspace_id=workspace_id)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/publish-preread", response_model=PublishPrereadResponse)
def publish_preread(
    meeting_id: uuid.UUID,
    request_session: Annotated[AuthenticatedSession, Depends(deps.current_session)],
    workspace_id: Annotated[str, Depends(deps.current_workspace)],
) -> dict[str, Any]:
    """Publish the board pack as a permissioned pre-read."""
    try:
        return prep.publish_preread(
            meeting_id, workspace_id=workspace_id, actor_id=request_session.principal_id
        )
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
