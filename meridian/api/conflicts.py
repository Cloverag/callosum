"""Entity Conflict review endpoints (Meridian P2, H-15).

Exposes entity conflict detection queue and human approval/rejection actions.
All operations execute under RLS and log audit events.
"""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from callosum import conflicts as engine_conflicts
from callosum import store
from meridian import audit
from meridian.api import deps

router = APIRouter(prefix="/api/conflicts", tags=["conflicts"])


class ConflictResponse(BaseModel):
    id: str
    name_a: str
    type_a: str
    name_b: str
    type_b: str
    similarity: float
    quote_a: str | None = None
    quote_b: str | None = None
    sensitivity: int
    status: str = "pending"
    #: Rendered by the conflict card ("Detected {date}") and declared on
    #: `EntityConflict` in `frontend/src/lib/api.ts`. It was selected by the query
    #: below and then dropped from the response, so the card has been formatting
    #: `new Date(undefined)` for as long as it has existed.
    created_at: datetime


@router.get("", response_model=list[ConflictResponse])
def list_conflicts(
    principal: deps.CurrentPrincipal,
    workspace_id: deps.CurrentWorkspace,
    status: str = Query("pending", description="Filter by conflict status (pending, approved, rejected)"),
    similarity_min: float = Query(0.0, description="Minimum similarity score (0.0 to 1.0)"),
) -> list[dict[str, Any]]:
    """List entity conflicts for the selected workspace."""
    with store.pg(workspace_id) as conn:
        rows = conn.execute(
            """
            SELECT id, name_a, type_a, name_b, type_b,
                   similarity, quote_a, quote_b, sensitivity, status, created_at
              FROM entity_conflict
             WHERE status = %s AND similarity >= %s AND sensitivity <= %s
             ORDER BY similarity DESC, created_at ASC
             LIMIT 100
            """,
            (status, similarity_min, principal.clearance),
        ).fetchall()

    return [
        {
            "id": str(r["id"]),
            "name_a": r["name_a"],
            "type_a": r["type_a"],
            "name_b": r["name_b"],
            "type_b": r["type_b"],
            "similarity": float(r["similarity"]),
            "quote_a": r["quote_a"],
            "quote_b": r["quote_b"],
            "sensitivity": r["sensitivity"],
            "status": r["status"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


@router.post("/{conflict_id}/approve")
def approve_conflict(
    conflict_id: uuid.UUID,
    principal: deps.CurrentPrincipal,
    workspace_id: deps.CurrentWorkspace,
) -> dict[str, Any]:
    """Approve an entity conflict, creating an ALIAS_OF graph edge."""
    # `store.neo()` builds a NEW driver, with its own connection pool, on every
    # call — the CLI callers are one-shot processes, so nothing there ever had to
    # close one. A request handler is not, so the driver is scoped to the request.
    try:
        with store.neo() as driver, store.pg(workspace_id) as conn:
            change_id = engine_conflicts.approve_conflict(
                conn, driver, conflict_id, reviewer_id=principal.id
            )
            audit.record_audit_event(
                conn,
                aggregate_type="audit",
                aggregate_id=conflict_id,
                action="status_changed",
                actor_principal_id=principal.id,
                payload={"status": "approved", "change_id": str(change_id)},
                workspace_id=workspace_id,
            )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return {"id": str(conflict_id), "status": "approved", "change_id": str(change_id)}


@router.post("/{conflict_id}/reject")
def reject_conflict(
    conflict_id: uuid.UUID,
    principal: deps.CurrentPrincipal,
    workspace_id: deps.CurrentWorkspace,
) -> dict[str, Any]:
    """Reject an entity conflict, marking the entities as distinct."""
    try:
        with store.pg(workspace_id) as conn:
            engine_conflicts.reject_conflict(
                conn, conflict_id, reviewer_id=principal.id
            )
            audit.record_audit_event(
                conn,
                aggregate_type="audit",
                aggregate_id=conflict_id,
                action="status_changed",
                actor_principal_id=principal.id,
                payload={"status": "rejected"},
                workspace_id=workspace_id,
            )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return {"id": str(conflict_id), "status": "rejected"}
