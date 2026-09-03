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
    ActorNotInWorkspace,
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
    # An actor must hold an active membership in the workspace being written to.
    # A principal row alone is not an actor anywhere — that is what CP5b established
    # and what `record_audit_event` now enforces.
    _admin(
        """
        INSERT INTO membership (principal_id, workspace_id, role, clearance, active)
        VALUES (%s, %s, 'founder', 4, true)
        """,
        (p_id, ws),
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
    # An actor must hold an active membership in the workspace being written to.
    # A principal row alone is not an actor anywhere — that is what CP5b established
    # and what `record_audit_event` now enforces.
    _admin(
        """
        INSERT INTO membership (principal_id, workspace_id, role, clearance, active)
        VALUES (%s, %s, 'founder', 4, true)
        """,
        (p_id, ws),
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


# ---------------------------------------------------------------------------
# Review findings (PR #61) — regression coverage
#
# Three defects found by probing the running schema rather than reading it:
# a cross-workspace actor reference that was accepted, unconstrained enum
# columns, and a workspace cascade that emptied the trail. Each is pinned here.
# ---------------------------------------------------------------------------

def _workspace(label: str) -> uuid.UUID:
    ws = uuid.uuid4()
    _admin(
        "INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s)",
        (ws, f"{label}-{ws.hex[:6]}", f"ext-{ws.hex[:6]}"),
    )
    return ws


def _principal_in(ws: uuid.UUID, name: str) -> uuid.UUID:
    pid = uuid.uuid4()
    _admin(
        "INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, 'director', 2)",
        (pid, name),
    )
    _admin(
        """
        INSERT INTO membership (principal_id, workspace_id, role, clearance, active)
        VALUES (%s, %s, 'director', 2, true)
        """,
        (pid, ws),
    )
    return pid


def _purge(*workspaces: uuid.UUID) -> None:
    for ws in workspaces:
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM membership WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM workspace WHERE id = %s", (ws,))


def test_actor_from_another_workspace_is_refused():
    """The finding that motivated the membership check.

    `actor_principal_id REFERENCES principal(id)` is validated as the table owner,
    which bypasses RLS, so the foreign key proves the principal exists but not that
    they belong here. Before the check in `record_audit_event()`, this insert
    succeeded — attributing an action to someone who was never in the workspace, in a
    table that cannot be corrected afterwards.
    """
    ws_a, ws_b = _workspace("actor-A"), _workspace("actor-B")
    try:
        outsider = _principal_in(ws_b, "Only In B")

        with store.pg(str(ws_a)) as conn:
            with pytest.raises(ActorNotInWorkspace):
                record_audit_event(
                    conn,
                    aggregate_type="meeting",
                    aggregate_id=uuid.uuid4(),
                    action="created",
                    actor_principal_id=outsider,
                    workspace_id=ws_a,
                )
    finally:
        _admin("DELETE FROM membership WHERE workspace_id = %s", (ws_b,))
        _purge(ws_a, ws_b)


def test_a_member_of_this_workspace_is_accepted():
    """The other half — the check must not refuse legitimate actors."""
    ws = _workspace("actor-ok")
    try:
        insider = _principal_in(ws, "Member Here")
        with store.pg(str(ws)) as conn:
            event = record_audit_event(
                conn,
                aggregate_type="meeting",
                aggregate_id=uuid.uuid4(),
                action="created",
                actor_principal_id=insider,
                workspace_id=ws,
            )
            assert str(event.actor_principal_id) == str(insider)
    finally:
        _purge(ws)


def test_an_unknown_actor_is_refused_identically_to_an_outsider():
    """No membership oracle: absent and not-a-member give the same error."""
    ws = _workspace("actor-ghost")
    try:
        with store.pg(str(ws)) as conn:
            with pytest.raises(ActorNotInWorkspace):
                record_audit_event(
                    conn,
                    aggregate_type="meeting",
                    aggregate_id=uuid.uuid4(),
                    action="created",
                    actor_principal_id=uuid.uuid4(),
                    workspace_id=ws,
                )
    finally:
        _purge(ws)


def test_an_actorless_event_is_still_allowed():
    """System-generated events have no principal behind them."""
    ws = _workspace("actor-none")
    try:
        with store.pg(str(ws)) as conn:
            event = record_audit_event(
                conn,
                aggregate_type="meeting",
                aggregate_id=uuid.uuid4(),
                action="created",
                workspace_id=ws,
            )
            assert event.actor_principal_id is None
    finally:
        _purge(ws)


def test_aggregate_type_and_action_are_constrained_by_the_DATABASE():
    """Asserted through the SUPERUSER connection, deliberately.

    The module validates both against its frozensets, but that only protects callers
    who go through it. This table is append-only with UPDATE revoked, so a row written
    with a typo'd type is invisible to the query meant to find it AND can never be
    corrected. Same reasoning as the FR-EXEC-03 CHECK in `0015_commitment`.
    """
    ws = _workspace("check")
    try:
        with psycopg.connect(settings().postgres_dsn) as conn:
            for column, value in (
                ("aggregate_type", "not_a_real_aggregate"),
                ("action", "teleported"),
            ):
                agg_type = value if column == "aggregate_type" else "meeting"
                action = value if column == "action" else "created"
                with pytest.raises(psycopg.errors.CheckViolation):
                    conn.execute(
                        """
                        INSERT INTO audit_event
                            (workspace_id, aggregate_type, aggregate_id, action)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (ws, agg_type, uuid.uuid4(), action),
                    )
                conn.rollback()
    finally:
        _purge(ws)


def test_membership_role_check_accepts_and_rejects_correctly():
    """`membership_role_check` (0027) is the security boundary option (c) rests on —
    it constrains the only column the future clearance mapping will key off. Proving
    the constraint was *created* (`pg_constraint` shows the definition) is not proof
    it *rejects* anything; those are different claims. A CHECK narrow enough to reject
    every value passes a rejection-only test exactly as well as a correct one, so this
    asserts both directions rather than only the negative one.

    Case sensitivity is deliberate, not incidental: Postgres `IN` is case-sensitive,
    so `'Founder'` is rejected on purpose alongside `'superuser'` and `''`. The
    vocabulary is the seven lowercase tokens exactly — if a future route ever accepts
    a role from a request body, it must validate against this same exact-match
    boundary rather than normalise case around it.
    """
    ws = _workspace("role-check")
    pid = uuid.uuid4()
    _admin(
        "INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, 'founder', 4)",
        (pid, f"Role-Check-{pid.hex[:6]}"),
    )
    try:
        with psycopg.connect(settings().postgres_dsn) as conn:
            # In-vocabulary: must succeed. Not padding — see docstring.
            conn.execute(
                """
                INSERT INTO membership (principal_id, workspace_id, role, clearance)
                VALUES (%s, %s, 'observer', 0)
                """,
                (pid, ws),
            )
            row = conn.execute(
                "SELECT role FROM membership WHERE principal_id = %s AND workspace_id = %s",
                (pid, ws),
            ).fetchone()
            assert row[0] == "observer"
            conn.execute(
                "DELETE FROM membership WHERE principal_id = %s AND workspace_id = %s",
                (pid, ws),
            )
            conn.commit()

            # Out-of-vocabulary: an unknown value, an empty string, and a
            # case-shifted in-vocabulary value all rejected.
            for bad_role in ("superuser", "", "Founder"):
                with pytest.raises(psycopg.errors.CheckViolation):
                    conn.execute(
                        """
                        INSERT INTO membership (principal_id, workspace_id, role, clearance)
                        VALUES (%s, %s, %s, 0)
                        """,
                        (pid, ws, bad_role),
                    )
                conn.rollback()
    finally:
        _purge(ws)
        _admin("DELETE FROM principal WHERE id = %s", (pid,))


def test_the_sql_check_and_the_python_frozensets_agree():
    """A drift between the two should fail loudly rather than rot.

    The CHECK constraint and `AGGREGATE_TYPES`/`ACTIONS` are maintained in different
    files. Reading the constraint back from the catalogue is what keeps them honest.
    """
    with psycopg.connect(settings().postgres_dsn, row_factory=dict_row) as conn:
        rows = conn.execute(
            """
            SELECT pg_get_constraintdef(oid) AS def
              FROM pg_constraint
             WHERE conrelid = 'audit_event'::regclass AND contype = 'c'
            """
        ).fetchall()
    definitions = " ".join(r["def"] for r in rows)

    for value in AGGREGATE_TYPES:
        assert f"'{value}'" in definitions, f"aggregate_type {value!r} missing from the CHECK"
    for value in ACTIONS:
        assert f"'{value}'" in definitions, f"action {value!r} missing from the CHECK"


def test_deleting_a_workspace_cannot_silently_erase_its_audit_trail():
    """Was ON DELETE CASCADE: 4 audit rows became 0 on a workspace delete.

    An audit log that a workspace deletion empties is the opposite of an audit log.
    RESTRICT forces whoever writes tenant offboarding to make retention explicit.
    """
    ws = _workspace("cascade")
    try:
        with store.pg(str(ws)) as conn:
            record_audit_event(
                conn,
                aggregate_type="meeting",
                aggregate_id=uuid.uuid4(),
                action="created",
                workspace_id=ws,
            )

        with psycopg.connect(settings().postgres_dsn) as conn:
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                conn.execute("DELETE FROM workspace WHERE id = %s", (ws,))
            conn.rollback()

        with psycopg.connect(settings().postgres_dsn, row_factory=dict_row) as conn:
            remaining = conn.execute(
                "SELECT count(*) AS n FROM audit_event WHERE workspace_id = %s", (ws,)
            ).fetchone()["n"]
        assert remaining == 1, "the trail must survive an attempted workspace delete"
    finally:
        _purge(ws)
