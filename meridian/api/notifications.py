"""Notification endpoints (Meridian P8, Issue #62)."""

from typing import Any
from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict

from meridian import notifications as domain
from meridian.api.deps import CurrentPrincipal

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class DispatchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    dispatched: int
    failed: int
    total_processed: int


@router.get("/pending")
def list_pending_notifications(principal: CurrentPrincipal) -> list[dict[str, Any]]:
    """Lists pending notification delivery items for the caller's workspace."""
    return domain.get_pending_deliveries(workspace_id=principal.workspace_id)


@router.post("/dispatch", status_code=status.HTTP_200_OK)
def dispatch_notifications(principal: CurrentPrincipal) -> DispatchResponse:
    """Triggers batch dispatch for pending commitment notifications."""
    res = domain.dispatch_pending_notifications(workspace_id=principal.workspace_id)
    return DispatchResponse(**res)
