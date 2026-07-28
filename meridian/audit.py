"""Audit Event domain — structured institutional memory audit trail (Meridian P2, checkpoint 8).

This module owns the immutable historical log of operations performed across all Meridian
domain aggregate roots (meetings, decisions, board packs, minutes, board members, resolutions,
commitments).

Design contract:
  - `record_audit_event()` executes inside the caller's open Postgres transaction (`conn`)
    to guarantee atomic commit/rollback alongside the domain aggregate mutation.
  - Immutability: `audit_event` rows are append-only. There is NO `update` or `delete` path,
    and DB privileges (`UPDATE, DELETE`) are revoked from `callosum_app`.
  - `list_audit_events()` executes through `store.pg(workspace_id)` under the `callosum_app`
    role so Row-Level Security automatically enforces tenant isolation.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg

from callosum import store
from callosum.store import DEFAULT_WORKSPACE_ID


class AuditValidationError(ValueError):
    """Raised when an invalid aggregate type, action, UUID, or payload is supplied."""


# Recognized aggregate root types in Meridian P2
AGGREGATE_TYPES = frozenset(
    {
        "meeting",
        "agenda_item",
        "document",
        "decision",
        "board_pack",
        "minutes",
        "board_member",
        "resolution",
        "commitment",
        "audit",
    }
)

# Recognized action types
ACTIONS = frozenset(
    {
        "created",
        "updated",
        "status_changed",
        "superseded",
        "published",
        "deleted",
        "voted",
        "reordered",
        "item_added",
        "item_removed",
        "recorded",
    }
)


@dataclass(frozen=True)
class AuditEvent:
    id: uuid.UUID
    workspace_id: uuid.UUID
    actor_principal_id: uuid.UUID | None
    aggregate_type: str
    aggregate_id: uuid.UUID
    action: str
    payload: dict[str, Any]
    created_at: datetime


def _row_to_audit_event(row: dict[str, Any]) -> AuditEvent:
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    elif payload is None:
        payload = {}

    return AuditEvent(
        id=row["id"],
        workspace_id=row["workspace_id"],
        actor_principal_id=row["actor_principal_id"],
        aggregate_type=row["aggregate_type"],
        aggregate_id=row["aggregate_id"],
        action=row["action"],
        payload=payload,
        created_at=row["created_at"],
    )


def record_audit_event(
    conn: psycopg.Connection,
    *,
    aggregate_type: str,
    aggregate_id: uuid.UUID | str,
    action: str,
    actor_principal_id: uuid.UUID | str | None = None,
    payload: dict[str, Any] | None = None,
    workspace_id: uuid.UUID | str = DEFAULT_WORKSPACE_ID,
) -> AuditEvent:
    """Record an append-only audit event inside the caller's open database transaction.

    This function MUST run within the domain aggregate mutation transaction (`conn`) to guarantee
    atomicity: if the domain mutation rolls back, the audit record is also rolled back.
    """
    if not aggregate_type or aggregate_type not in AGGREGATE_TYPES:
        raise AuditValidationError(
            f"Invalid aggregate_type '{aggregate_type}'. Must be one of {sorted(AGGREGATE_TYPES)}"
        )

    if not action or action not in ACTIONS:
        raise AuditValidationError(
            f"Invalid action '{action}'. Must be one of {sorted(ACTIONS)}"
        )

    try:
        agg_uuid = uuid.UUID(str(aggregate_id)) if not isinstance(aggregate_id, uuid.UUID) else aggregate_id
    except (ValueError, TypeError, AttributeError) as exc:
        raise AuditValidationError(f"Invalid aggregate_id: '{aggregate_id}'") from exc

    actor_uuid = None
    if actor_principal_id is not None:
        try:
            actor_uuid = (
                uuid.UUID(str(actor_principal_id))
                if not isinstance(actor_principal_id, uuid.UUID)
                else actor_principal_id
            )
        except (ValueError, TypeError, AttributeError) as exc:
            raise AuditValidationError(f"Invalid actor_principal_id: '{actor_principal_id}'") from exc

    try:
        ws_uuid = uuid.UUID(str(workspace_id)) if not isinstance(workspace_id, uuid.UUID) else workspace_id
    except (ValueError, TypeError, AttributeError) as exc:
        raise AuditValidationError(f"Invalid workspace_id: '{workspace_id}'") from exc

    payload_json = json.dumps(payload or {})

    row = conn.execute(
        """
        INSERT INTO audit_event
            (workspace_id, actor_principal_id, aggregate_type, aggregate_id, action, payload)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        RETURNING id, workspace_id, actor_principal_id, aggregate_type, aggregate_id, action, payload, created_at
        """,
        (str(ws_uuid), str(actor_uuid) if actor_uuid else None, aggregate_type, agg_uuid, action, payload_json),
    ).fetchone()

    return _row_to_audit_event(row)


def list_audit_events(
    *,
    aggregate_type: str | None = None,
    aggregate_id: uuid.UUID | str | None = None,
    actor_principal_id: uuid.UUID | str | None = None,
    action: str | None = None,
    limit: int = 50,
    offset: int = 0,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> list[AuditEvent]:
    """Retrieve tenant-isolated audit log entries.

    Executes through `store.pg(workspace_id)` under the `callosum_app` role so Postgres
    Row-Level Security automatically enforces workspace isolation.
    """
    if limit <= 0:
        raise AuditValidationError(f"limit must be positive, got {limit}")
    if limit > 500:
        raise AuditValidationError(f"limit cannot exceed 500, got {limit}")
    if offset < 0:
        raise AuditValidationError(f"offset cannot be negative, got {offset}")

    conditions = []
    params: list[Any] = []

    if aggregate_type is not None:
        if aggregate_type not in AGGREGATE_TYPES:
            raise AuditValidationError(f"Invalid aggregate_type '{aggregate_type}' filter")
        conditions.append("aggregate_type = %s")
        params.append(aggregate_type)

    if aggregate_id is not None:
        try:
            agg_uuid = uuid.UUID(str(aggregate_id)) if not isinstance(aggregate_id, uuid.UUID) else aggregate_id
        except (ValueError, TypeError, AttributeError) as exc:
            raise AuditValidationError(f"Invalid aggregate_id filter: '{aggregate_id}'") from exc
        conditions.append("aggregate_id = %s")
        params.append(agg_uuid)

    if actor_principal_id is not None:
        try:
            actor_uuid = (
                uuid.UUID(str(actor_principal_id))
                if not isinstance(actor_principal_id, uuid.UUID)
                else actor_principal_id
            )
        except (ValueError, TypeError, AttributeError) as exc:
            raise AuditValidationError(f"Invalid actor_principal_id filter: '{actor_principal_id}'") from exc
        conditions.append("actor_principal_id = %s")
        params.append(actor_uuid)

    if action is not None:
        if action not in ACTIONS:
            raise AuditValidationError(f"Invalid action '{action}' filter")
        conditions.append("action = %s")
        params.append(action)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT id, workspace_id, actor_principal_id, aggregate_type, aggregate_id, action, payload, created_at
          FROM audit_event
        {where_clause}
      ORDER BY created_at DESC, id DESC
         LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])

    with store.pg(workspace_id=workspace_id) as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()

    return [_row_to_audit_event(r) for r in rows]


def get_audit_event(
    event_id: uuid.UUID | str,
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> AuditEvent | None:
    """Fetch a single audit event by ID within tenant RLS scope."""
    try:
        e_uuid = uuid.UUID(str(event_id)) if not isinstance(event_id, uuid.UUID) else event_id
    except (ValueError, TypeError, AttributeError) as exc:
        raise AuditValidationError(f"Invalid event_id: '{event_id}'") from exc

    with store.pg(workspace_id=workspace_id) as conn:
        row = conn.execute(
            """
            SELECT id, workspace_id, actor_principal_id, aggregate_type, aggregate_id, action, payload, created_at
              FROM audit_event
             WHERE id = %s
            """,
            (e_uuid,),
        ).fetchone()

    return _row_to_audit_event(row) if row else None
