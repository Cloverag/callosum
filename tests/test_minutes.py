"""Live-store integration coverage for the P2 Minutes aggregate (Meridian, checkpoint 3).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``. These tests
exercise the minutes domain against a real Postgres: directional meeting locks (minutes require
in_progress/completed meeting), finalization immutability, supersession lineage, optimistic concurrency,
and Row-Level Security tenant isolation across workspaces.
"""

from datetime import datetime, timedelta, timezone
import os
import uuid

import pytest

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip("set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests", allow_module_level=True)

import psycopg

from callosum.config import settings
from meridian import meetings, minutes
from meridian.minutes import (
    DRAFT,
    FINAL,
    MinutesLockedError,
    MinutesNotFound,
    MinutesValidationError,
    StaleMinutesError,
)

pytestmark = pytest.mark.integration


def _admin(sql: str, params: tuple = ()) -> None:
    """Run a control-plane statement as the superuser (bypasses RLS by design)."""
    with psycopg.connect(settings().postgres_dsn) as conn:
        conn.execute(sql, params)
        conn.commit()


def _new_workspace() -> str:
    ws = str(uuid.uuid4())
    _admin(
        "INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s)",
        (ws, f"test-{ws[:8]}", ws),
    )
    return ws


def _cleanup(*workspace_ids: str) -> None:
    for ws in workspace_ids:
        _admin("DELETE FROM minutes WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM meeting WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM workspace WHERE id = %s", (ws,))


def _create_live_meeting(ws: str) -> meetings.Meeting:
    now_dt = datetime.now(timezone.utc)
    m = meetings.create_meeting(
        "Live Meeting",
        scheduled_start=now_dt,
        scheduled_end=now_dt + timedelta(hours=1),
        workspace_id=ws,
    )
    m = meetings.transition_status(m.id, meetings.SCHEDULED, expected_version=1, workspace_id=ws)
    m = meetings.transition_status(m.id, meetings.IN_PROGRESS, expected_version=2, workspace_id=ws)
    return m


def test_create_and_get_minutes():
    ws = _new_workspace()
    try:
        m = _create_live_meeting(ws)

        min_rec = minutes.create_minutes(
            m.id, "Meeting called to order at 4:00 PM. Budget approved.", workspace_id=ws
        )
        assert min_rec.meeting_id == m.id
        assert min_rec.body == "Meeting called to order at 4:00 PM. Budget approved."
        assert min_rec.status == DRAFT
        assert min_rec.version_no == 1
        assert min_rec.version == 1

        fetched = minutes.get_minutes(min_rec.id, workspace_id=ws)
        assert fetched.id == min_rec.id
        assert fetched.body == min_rec.body
    finally:
        _cleanup(ws)


def test_create_minutes_on_draft_meeting_raises_locked_error():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Draft Meeting", workspace_id=ws)

        # Minutes cannot be created on a draft meeting
        with pytest.raises(MinutesLockedError):
            minutes.create_minutes(m.id, "Premature minutes", workspace_id=ws)
    finally:
        _cleanup(ws)


def test_update_and_finalise_minutes():
    ws = _new_workspace()
    try:
        m = _create_live_meeting(ws)
        min_rec = minutes.create_minutes(m.id, "Initial Draft Minutes", workspace_id=ws)

        # Update draft
        updated = minutes.update_minutes(
            min_rec.id, expected_version=1, workspace_id=ws, body="Revised Draft Minutes"
        )
        assert updated.body == "Revised Draft Minutes"
        assert updated.version == 2

        # Finalise minutes
        finalised = minutes.finalise_minutes(min_rec.id, expected_version=2, workspace_id=ws)
        assert finalised.status == FINAL
        assert finalised.finalised_at is not None
        assert finalised.version == 3
    finally:
        _cleanup(ws)


def test_finalised_minutes_are_immutable():
    ws = _new_workspace()
    try:
        m = _create_live_meeting(ws)
        min_rec = minutes.create_minutes(m.id, "Final Minutes Body", workspace_id=ws)
        finalised = minutes.finalise_minutes(min_rec.id, expected_version=1, workspace_id=ws)

        # Updating finalised minutes raises MinutesLockedError
        with pytest.raises(MinutesLockedError):
            minutes.update_minutes(
                finalised.id, expected_version=2, workspace_id=ws, body="Attempted Edit"
            )
    finally:
        _cleanup(ws)


def test_supersede_finalised_minutes():
    ws = _new_workspace()
    try:
        m = _create_live_meeting(ws)
        m1 = minutes.create_minutes(m.id, "Original Minutes v1", workspace_id=ws)
        m1 = minutes.finalise_minutes(m1.id, expected_version=1, workspace_id=ws)

        # Supersede m1 with m2
        m2, m1_updated = minutes.supersede_minutes(
            m1.id, "Amended Minutes v2", expected_version=2, workspace_id=ws
        )

        assert m2.body == "Amended Minutes v2"
        assert m2.status == DRAFT
        assert m2.version_no == 2

        assert m1_updated.superseded_by_id == m2.id

        # Verify old minutes in store retains link to new minutes
        fetched_old = minutes.get_minutes(m1.id, workspace_id=ws)
        assert fetched_old.superseded_by_id == m2.id
    finally:
        _cleanup(ws)


def test_cross_workspace_isolation():
    ws_a = _new_workspace()
    ws_b = _new_workspace()
    try:
        m_a = _create_live_meeting(ws_a)
        min_a = minutes.create_minutes(m_a.id, "Secret Minutes A", workspace_id=ws_a)

        # Workspace B cannot see or modify A's minutes
        assert minutes.list_minutes(m_a.id, workspace_id=ws_b) == []

        with pytest.raises(MinutesNotFound):
            minutes.get_minutes(min_a.id, workspace_id=ws_b)

        with pytest.raises(MinutesNotFound):
            minutes.update_minutes(min_a.id, expected_version=1, workspace_id=ws_b, body="Hacked")
    finally:
        _cleanup(ws_a, ws_b)


def test_optimistic_concurrency():
    ws = _new_workspace()
    try:
        m = _create_live_meeting(ws)
        min_rec = minutes.create_minutes(m.id, "Original Minutes", workspace_id=ws)

        # Update 1 -> version 2
        updated = minutes.update_minutes(
            min_rec.id, expected_version=1, workspace_id=ws, body="New Minutes"
        )
        assert updated.version == 2

        # Update 2 with stale version 1 -> raises StaleMinutesError
        with pytest.raises(StaleMinutesError):
            minutes.update_minutes(min_rec.id, expected_version=1, workspace_id=ws, body="Stale Minutes")
    finally:
        _cleanup(ws)


def test_minutes_validation_errors():
    ws = _new_workspace()
    try:
        m = _create_live_meeting(ws)

        # Empty body creation
        with pytest.raises(MinutesValidationError):
            minutes.create_minutes(m.id, "   ", workspace_id=ws)

        min_rec = minutes.create_minutes(m.id, "Valid Minutes Body", workspace_id=ws)

        # No fields to update
        with pytest.raises(MinutesValidationError):
            minutes.update_minutes(min_rec.id, expected_version=1, workspace_id=ws)

        # Empty body update
        with pytest.raises(MinutesValidationError):
            minutes.update_minutes(min_rec.id, expected_version=1, workspace_id=ws, body="   ")

        # Superseding draft minutes (only final minutes can be superseded)
        with pytest.raises(MinutesValidationError):
            minutes.supersede_minutes(min_rec.id, "New Body", expected_version=1, workspace_id=ws)

        # Finalise minutes
        finalised = minutes.finalise_minutes(min_rec.id, expected_version=1, workspace_id=ws)

        # Finalising already finalised minutes raises MinutesValidationError
        with pytest.raises(MinutesValidationError):
            minutes.finalise_minutes(finalised.id, expected_version=2, workspace_id=ws)
    finally:
        _cleanup(ws)


def test_minutes_clearance_model_is_workspace_scoped_by_design():
    """ADR-015 (Issue #49): `minutes` records are workspace-scoped via RLS.

    They carry no `sensitivity` column and take no `clearance` argument.
    """
    ws = uuid.uuid4()
    m_id = uuid.uuid4()
    _admin("INSERT INTO workspace (id, name) VALUES (%s, 'Minutes ADR015')", (ws,))
    _admin(
        "INSERT INTO meeting (id, workspace_id, title, status) VALUES (%s, %s, 'Board Meeting ADR015', 'in_progress')",
        (m_id, ws),
    )

    try:
        # Create minutes without passing clearance
        min_rec = minutes.create_minutes(
            m_id,
            body="Approved expansion plans and budget allocation.",
            workspace_id=str(ws),
        )
        assert min_rec.workspace_id == str(ws)
        assert not hasattr(min_rec, "sensitivity")
        assert not hasattr(min_rec, "clearance")

        # Fetch minutes without passing clearance
        fetched = minutes.get_minutes(min_rec.id, workspace_id=str(ws))
        assert fetched is not None
        assert fetched.id == min_rec.id
    finally:
        _cleanup(ws)




