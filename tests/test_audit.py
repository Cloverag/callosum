"""Integration & unit test coverage for Checkpoint 8 — Audit Event aggregate root (`meridian/audit.py`).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest tests/test_audit.py -v``.

Coverage requirements:
  - Append-only immutability: UPDATE and DELETE operations on `audit_event` under `callosum_app`
    must be rejected with `psycopg.errors.InsufficientPrivilege`.
  - Multi-tenant isolation: An audit event created in Workspace Alpha is invisible to Workspace Beta.
  - Transactional atomicity: A transaction rollback discards the recorded audit event atomically.
  - Domain filtering & validation: Filter logic, pagination, and invalid input guards.
"""

import os
import uuid

import pytest

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip("set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests", allow_module_level=True)

import psycopg
from psycopg.rows import dict_row

from callosum import store
from callosum.config import settings
from meridian.audit import (
    ACTIONS,
    AGGREGATE_TYPES,
    AuditEvent,
    AuditValidationError,
    get_audit_event,
    list_audit_events,
    record_audit_event,
)

pytestmark = pytest.mark.integration


def _admin(sql: str, params: tuple = ()) -> None:
    """Run a control-plane statement as superuser (bypasses RLS)."""
    with psycopg.connect(settings().postgres_dsn) as conn:
        conn.execute(sql, params)
        conn.commit()


def test_record_and_get_audit_event():
    """Verify recording a structured audit event within an open transaction."""
    ws = uuid.uuid4()
    p_id = uuid.uuid4()
    agg_id = uuid.uuid4()

    _admin(
        "INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s)",
        (ws, f"Audit-WS-{ws.hex[:6]}", f"ext-{ws.hex[:6]}"),
    )
    _admin(
        "INSERT INTO principal (id, name, email, role, clearance) VALUES (%s, %s, %s, 'founder', 4)",
        (p_id, f"Actor-{p_id.hex[:6]}", f"actor-{p_id.hex[:6]}@example.com"),
    )

    try:
        with store.pg(workspace_id=str(ws)) as conn:
            event = record_audit_event(
                conn,
                aggregate_type="decision",
                aggregate_id=agg_id,
                action="created",
                actor_principal_id=p_id,
                payload={"title": "Approve Q3 Budget", "amount": 50000},
                workspace_id=ws,
            )
            conn.commit()

        assert isinstance(event, AuditEvent)
        assert event.workspace_id == ws
        assert event.actor_principal_id == p_id
        assert event.aggregate_type == "decision"
        assert event.aggregate_id == agg_id
        assert event.action == "created"
        assert event.payload == {"title": "Approve Q3 Budget", "amount": 50000}

        # Fetch via get_audit_event
        fetched = get_audit_event(event.id, workspace_id=str(ws))
        assert fetched is not None
        assert fetched.id == event.id
        assert fetched.payload == {"title": "Approve Q3 Budget", "amount": 50000}
    finally:
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM principal WHERE id = %s", (p_id,))
        _admin("DELETE FROM workspace WHERE id = %s", (ws,))


def test_audit_event_immutability():
    """`UPDATE` and `DELETE` on `audit_event` under `callosum_app` MUST raise InsufficientPrivilege."""
    ws = uuid.uuid4()
    agg_id = uuid.uuid4()

    _admin(
        "INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s)",
        (ws, f"Immut-WS-{ws.hex[:6]}", f"ext-{ws.hex[:6]}"),
    )

    try:
        with store.pg(workspace_id=str(ws)) as conn:
            event = record_audit_event(
                conn,
                aggregate_type="meeting",
                aggregate_id=agg_id,
                action="created",
                workspace_id=ws,
            )
            conn.commit()

        # Direct UPDATE attempt under callosum_app role -> MUST FAIL
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with store.pg(workspace_id=str(ws)) as conn:
                conn.execute(
                    "UPDATE audit_event SET action = 'tampered' WHERE id = %s",
                    (event.id,),
                )

        # Direct DELETE attempt under callosum_app role -> MUST FAIL
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with store.pg(workspace_id=str(ws)) as conn:
                conn.execute(
                    "DELETE FROM audit_event WHERE id = %s",
                    (event.id,),
                )
    finally:
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM workspace WHERE id = %s", (ws,))


def test_cross_workspace_audit_isolation():
    """Audit events created in Workspace Alpha are completely invisible to Workspace Beta."""
    wa, wb = uuid.uuid4(), uuid.uuid4()
    agg_a, agg_b = uuid.uuid4(), uuid.uuid4()

    _admin(
        "INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s), (%s, %s, %s)",
        (wa, f"Alpha-{wa.hex[:6]}", f"a-{wa.hex[:6]}", wb, f"Beta-{wb.hex[:6]}", f"b-{wb.hex[:6]}"),
    )

    try:
        with store.pg(workspace_id=str(wa)) as conn:
            record_audit_event(
                conn, aggregate_type="commitment", aggregate_id=agg_a, action="created", workspace_id=wa
            )
            conn.commit()

        with store.pg(workspace_id=str(wb)) as conn:
            record_audit_event(
                conn, aggregate_type="commitment", aggregate_id=agg_b, action="created", workspace_id=wb
            )
            conn.commit()

        # Query Alpha: sees ONLY Alpha's event
        alpha_events = list_audit_events(workspace_id=str(wa))
        assert len(alpha_events) == 1
        assert alpha_events[0].aggregate_id == agg_a

        # Query Beta: sees ONLY Beta's event
        beta_events = list_audit_events(workspace_id=str(wb))
        assert len(beta_events) == 1
        assert beta_events[0].aggregate_id == agg_b

        # Direct fetch across workspace returns None due to RLS
        assert get_audit_event(alpha_events[0].id, workspace_id=str(wb)) is None
    finally:
        _admin("DELETE FROM audit_event WHERE workspace_id IN (%s, %s)", (wa, wb))
        _admin("DELETE FROM workspace WHERE id IN (%s, %s)", (wa, wb))


def test_transactional_rollback():
    """Rolling back the outer domain transaction discards the audit event atomically."""
    ws = uuid.uuid4()
    agg_id = uuid.uuid4()

    _admin(
        "INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s)",
        (ws, f"Rollback-WS-{ws.hex[:6]}", f"ext-{ws.hex[:6]}"),
    )

    try:
        with store.pg(workspace_id=str(ws)) as conn:
            event = record_audit_event(
                conn,
                aggregate_type="resolution",
                aggregate_id=agg_id,
                action="voted",
                workspace_id=ws,
            )
            # Explicit transaction rollback
            conn.rollback()

        # Event should NOT exist in database
        assert get_audit_event(event.id, workspace_id=str(ws)) is None
    finally:
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM workspace WHERE id = %s", (ws,))


def test_list_audit_events_filtering_and_pagination():
    """Test filtering audit logs by aggregate_type, aggregate_id, actor_principal_id, and action."""
    ws = uuid.uuid4()
    p_id = uuid.uuid4()
    agg_1, agg_2 = uuid.uuid4(), uuid.uuid4()

    _admin(
        "INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s)",
        (ws, f"Filter-WS-{ws.hex[:6]}", f"ext-{ws.hex[:6]}"),
    )
    _admin(
        "INSERT INTO principal (id, name, email, role, clearance) VALUES (%s, %s, %s, 'founder', 4)",
        (p_id, f"Actor-{p_id.hex[:6]}", f"actor-{p_id.hex[:6]}@example.com"),
    )

    try:
        with store.pg(workspace_id=str(ws)) as conn:
            record_audit_event(
                conn, aggregate_type="board_member", aggregate_id=agg_1, action="created", actor_principal_id=p_id, workspace_id=ws
            )
            record_audit_event(
                conn, aggregate_type="board_member", aggregate_id=agg_1, action="updated", actor_principal_id=p_id, workspace_id=ws
            )
            record_audit_event(
                conn, aggregate_type="resolution", aggregate_id=agg_2, action="status_changed", workspace_id=ws
            )
            conn.commit()

        # Filter by aggregate_type
        bm_events = list_audit_events(aggregate_type="board_member", workspace_id=str(ws))
        assert len(bm_events) == 2
        assert all(e.aggregate_type == "board_member" for e in bm_events)

        # Filter by aggregate_id
        agg1_events = list_audit_events(aggregate_id=agg_1, workspace_id=str(ws))
        assert len(agg1_events) == 2

        # Filter by actor_principal_id
        actor_events = list_audit_events(actor_principal_id=p_id, workspace_id=str(ws))
        assert len(actor_events) == 2

        # Filter by action
        updated_events = list_audit_events(action="updated", workspace_id=str(ws))
        assert len(updated_events) == 1
        assert updated_events[0].action == "updated"

        # Pagination test
        page_1 = list_audit_events(limit=2, offset=0, workspace_id=str(ws))
        assert len(page_1) == 2
        page_2 = list_audit_events(limit=2, offset=2, workspace_id=str(ws))
        assert len(page_2) == 1
    finally:
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM principal WHERE id = %s", (p_id,))
        _admin("DELETE FROM workspace WHERE id = %s", (ws,))


def test_audit_validation_errors():
    """Verify edge case validation guards raise AuditValidationError."""
    ws = uuid.uuid4()
    agg_id = uuid.uuid4()

    with store.pg(workspace_id=str(ws)) as conn:
        # Invalid aggregate_type
        with pytest.raises(AuditValidationError, match="Invalid aggregate_type"):
            record_audit_event(conn, aggregate_type="unknown_type", aggregate_id=agg_id, action="created", workspace_id=ws)

        # Invalid action
        with pytest.raises(AuditValidationError, match="Invalid action"):
            record_audit_event(conn, aggregate_type="decision", aggregate_id=agg_id, action="unknown_action", workspace_id=ws)

        # Invalid aggregate_id
        with pytest.raises(AuditValidationError, match="Invalid aggregate_id"):
            record_audit_event(conn, aggregate_type="decision", aggregate_id="not-a-uuid", action="created", workspace_id=ws)

        # Invalid actor_principal_id
        with pytest.raises(AuditValidationError, match="Invalid actor_principal_id"):
            record_audit_event(conn, aggregate_type="decision", aggregate_id=agg_id, action="created", actor_principal_id="invalid", workspace_id=ws)

    # Invalid pagination options
    with pytest.raises(AuditValidationError, match="limit must be positive"):
        list_audit_events(limit=0)

    with pytest.raises(AuditValidationError, match="limit cannot exceed 500"):
        list_audit_events(limit=600)

    with pytest.raises(AuditValidationError, match="offset cannot be negative"):
        list_audit_events(offset=-1)
