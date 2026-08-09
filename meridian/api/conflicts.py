"""Entity Conflict review endpoints (Meridian P2, H-15).

Exposes entity conflict detection queue and human approval/rejection actions.
All operations execute under RLS and log audit events.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from callosum import conflicts as engine_conflicts
from callosum import store
from meridian import audit
from meridian.api import deps
from meridian.api.session import AuthenticatedSession

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


@router.get("", response_model=list[ConflictResponse])
def list_conflicts(
    request_session: Annotated[AuthenticatedSession, Depends(deps.current_session)],
    workspace_id: Annotated[str, Depends(deps.current_workspace)],
    status: str = Query("pending", description="Filter by conflict status (pending, approved, rejected)"),
    similarity_min: float = Query(0.0, description="Minimum similarity score (0.0 to 1.0)"),
) -> list[dict[str, Any]]:
    """List entity conflicts for the selected workspace."""
    principal = deps.resolve_principal(request_session.principal_id, workspace_id)
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
        }
        for r in rows
    ]


@router.post("/{conflict_id}/approve")
def approve_conflict(
    conflict_id: uuid.UUID,
    request_session: Annotated[AuthenticatedSession, Depends(deps.current_session)],
    workspace_id: Annotated[str, Depends(deps.current_workspace)],
) -> dict[str, Any]:
    """Approve an entity conflict, creating an ALIAS_OF graph edge."""
    driver = store.connect_neo4j()
    try:
        with store.pg(workspace_id) as conn:
            change_id = engine_conflicts.approve_conflict(
                conn, driver, conflict_id, reviewer_id=uuid.UUID(request_session.principal_id)
            )
            audit.record_audit_event(
                conn,
                aggregate_type="audit",
                aggregate_id=conflict_id,
                action="status_changed",
                actor_principal_id=request_session.principal_id,
                payload={"status": "approved", "change_id": str(change_id)},
                workspace_id=workspace_id,
            )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return {"id": str(conflict_id), "status": "approved", "change_id": str(change_id)}


@router.post("/{conflict_id}/reject")
def reject_conflict(
    conflict_id: uuid.UUID,
    request_session: Annotated[AuthenticatedSession, Depends(deps.current_session)],
    workspace_id: Annotated[str, Depends(deps.current_workspace)],
) -> dict[str, Any]:
    """Reject an entity conflict, marking the entities as distinct."""
    try:
        with store.pg(workspace_id) as conn:
            engine_conflicts.reject_conflict(
                conn, conflict_id, reviewer_id=uuid.UUID(request_session.principal_id)
            )
            audit.record_audit_event(
                conn,
                aggregate_type="audit",
                aggregate_id=conflict_id,
                action="status_changed",
                actor_principal_id=request_session.principal_id,
                payload={"status": "rejected"},
                workspace_id=workspace_id,
            )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return {"id": str(conflict_id), "status": "rejected"}
