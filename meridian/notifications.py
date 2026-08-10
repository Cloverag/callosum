"""Notification Delivery Dispatcher Engine (Meridian P8, Issue #62).

Owns background worker dispatching, exponential retry calculations, and external
notification status tracking for commitments and board updates.
"""

import uuid
from typing import Any
from datetime import datetime, timezone, timedelta

from callosum import store
from callosum.store import DEFAULT_WORKSPACE_ID
from meridian import audit, commitments


class NotificationDispatchError(ValueError):
    """Base exception for notification dispatch operations."""


def calculate_retry_delay(attempts: int) -> timedelta:
    """Calculates exponential backoff retry delay based on attempt count.
    
    1st attempt: 1 min, 2nd: 2 min, 3rd: 4 min, 4th: 8 min, 5th: 16 min.
    """
    if attempts <= 0:
        return timedelta(minutes=0)
    delay_minutes = min(2 ** (attempts - 1), 60)
    return timedelta(minutes=delay_minutes)


def get_pending_deliveries(
    *, workspace_id: str = DEFAULT_WORKSPACE_ID
) -> list[dict[str, Any]]:
    """Fetches commitment notification deliveries requiring dispatch or retry."""
    with store.pg(workspace_id) as conn:
        rows = conn.execute(
            """
            SELECT id, title, owner_board_member_id, due_date, status,
                   delivery_status, delivery_attempts, external_system, external_task_id, version, updated_at
              FROM commitment
             WHERE workspace_id = %s
               AND (delivery_status = 'pending' OR (delivery_status = 'failed' AND delivery_attempts < 5))
             ORDER BY created_at ASC
            """,
            (workspace_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def dispatch_pending_notifications(
    *, workspace_id: str = DEFAULT_WORKSPACE_ID, max_attempts: int = 5
) -> dict[str, Any]:
    """Processes and dispatches pending commitment notifications for a workspace.

    Locks rows with `FOR UPDATE SKIP LOCKED`, simulates external webhook/channel
    notification dispatch, and records the delivery attempt outcome.
    """
    dispatched_count = 0
    failed_count = 0

    with store.pg(workspace_id) as conn:
        # Lock candidate rows
        candidates = conn.execute(
            """
            SELECT id, version, delivery_attempts, title
              FROM commitment
             WHERE workspace_id = %s
               AND (delivery_status = 'pending' OR (delivery_status = 'failed' AND delivery_attempts < %s))
             ORDER BY created_at ASC
             FOR UPDATE SKIP LOCKED
            """,
            (workspace_id, max_attempts),
        ).fetchall()

        for row in candidates:
            c_id = str(row["id"])
            version = row["version"]
            attempts = row["delivery_attempts"]

            # Simulate dispatch
            ext_system = "slack_webhook"
            ext_task_id = f"msg_{uuid.uuid4().hex[:12]}"

            try:
                commitments.record_delivery_attempt(
                    c_id,
                    commitments.DELIVERED,
                    expected_version=version,
                    workspace_id=workspace_id,
                    external_system=ext_system,
                    external_task_id=ext_task_id,
                    conn=conn,
                )
                audit.record_audit_event(
                    conn,
                    aggregate_type="commitment",
                    aggregate_id=uuid.UUID(c_id),
                    action="status_changed",
                    payload={
                        "external_system": ext_system,
                        "external_task_id": ext_task_id,
                        "attempt": attempts + 1,
                        "detail": "notification_delivered",
                    },
                    workspace_id=workspace_id,
                )
                dispatched_count += 1
            except Exception as e:
                failed_count += 1
                try:
                    commitments.record_delivery_attempt(
                        c_id,
                        commitments.FAILED,
                        expected_version=version,
                        workspace_id=workspace_id,
                        conn=conn,
                    )
                except Exception:
                    pass

    return {
        "workspace_id": workspace_id,
        "dispatched": dispatched_count,
        "failed": failed_count,
        "total_processed": dispatched_count + failed_count,
    }
