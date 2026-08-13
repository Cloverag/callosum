"""Live-store integration coverage for the P2 meeting aggregate (Meridian, checkpoint 1).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``. These tests
exercise the meeting domain against a real Postgres: the lifecycle state machine,
the optimistic-concurrency guard, the draft->scheduled time invariant, and — most
importantly — that Row-Level Security keeps one workspace's meetings invisible to
another. They create uniquely-id'd workspaces and delete only their own rows.

Setup/teardown of workspaces uses the admin DSN (bypasses RLS by design — control
plane, not tenant traffic); everything the domain does goes through ``store.pg()``
as the ``callosum_app`` role, which is where RLS actually bites.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip("set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests", allow_module_level=True)

import psycopg

from callosum.config import settings
from meridian import meetings
from meridian.meetings import (
    InvalidTransition,
    MeetingNotFound,
    MeetingValidationError,
    StaleMeetingError,
)

pytestmark = pytest.mark.integration

_START = datetime(2026, 8, 1, 14, 0, tzinfo=timezone.utc)
_END = _START + timedelta(hours=1)


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
        # meeting has no ON DELETE CASCADE, so clear its rows before the workspace.
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM meeting WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM membership WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM workspace WHERE id = %s", (ws,))


def test_create_and_get_meeting():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Q3 Board Meeting", workspace_id=ws)
        assert m.status == meetings.DRAFT
        assert m.version == 1
        assert m.workspace_id == ws

        fetched = meetings.get_meeting(m.id, workspace_id=ws)
        assert fetched.id == m.id
        assert fetched.title == "Q3 Board Meeting"
    finally:
        _cleanup(ws)


def test_full_lifecycle_transitions_bump_version():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting(
            "Lifecycle", workspace_id=ws, scheduled_start=_START, scheduled_end=_END
        )
        assert (m.status, m.version) == (meetings.DRAFT, 1)

        m = meetings.transition_status(m.id, meetings.SCHEDULED, expected_version=1, workspace_id=ws)
        assert (m.status, m.version) == (meetings.SCHEDULED, 2)

        m = meetings.transition_status(m.id, meetings.IN_PROGRESS, expected_version=2, workspace_id=ws)
        assert (m.status, m.version) == (meetings.IN_PROGRESS, 3)

        m = meetings.transition_status(m.id, meetings.COMPLETED, expected_version=3, workspace_id=ws)
        assert (m.status, m.version) == (meetings.COMPLETED, 4)
    finally:
        _cleanup(ws)


def test_invalid_transition_is_rejected():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting(
            "Skip", workspace_id=ws, scheduled_start=_START, scheduled_end=_END
        )
        # draft -> completed is not a legal edge.
        with pytest.raises(InvalidTransition):
            meetings.transition_status(m.id, meetings.COMPLETED, expected_version=1, workspace_id=ws)
    finally:
        _cleanup(ws)


def test_terminal_status_has_no_exit():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Cancel me", workspace_id=ws)
        m = meetings.transition_status(m.id, meetings.CANCELLED, expected_version=1, workspace_id=ws)
        assert m.status == meetings.CANCELLED
        # cancelled is terminal — nothing may follow it.
        with pytest.raises(InvalidTransition):
            meetings.transition_status(m.id, meetings.SCHEDULED, expected_version=m.version, workspace_id=ws)
    finally:
        _cleanup(ws)


def test_scheduling_requires_a_time_window():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("No time yet", workspace_id=ws)  # no start/end
        with pytest.raises(MeetingValidationError):
            meetings.transition_status(m.id, meetings.SCHEDULED, expected_version=1, workspace_id=ws)

        # Set the window, then scheduling is allowed.
        m = meetings.update_meeting(
            m.id, expected_version=1, workspace_id=ws,
            scheduled_start=_START, scheduled_end=_END,
        )
        m = meetings.transition_status(m.id, meetings.SCHEDULED, expected_version=m.version, workspace_id=ws)
        assert m.status == meetings.SCHEDULED
    finally:
        _cleanup(ws)


def test_optimistic_concurrency_conflict():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Concurrent", workspace_id=ws)  # version 1
        meetings.update_meeting(m.id, expected_version=1, workspace_id=ws, title="Renamed")  # -> version 2

        # A second writer still holding version 1 must be refused.
        with pytest.raises(StaleMeetingError):
            meetings.update_meeting(m.id, expected_version=1, workspace_id=ws, location="Room B")
        with pytest.raises(StaleMeetingError):
            meetings.transition_status(m.id, meetings.CANCELLED, expected_version=1, workspace_id=ws)
    finally:
        _cleanup(ws)


def test_meetings_are_isolated_across_workspaces():
    ws_a = _new_workspace()
    ws_b = _new_workspace()
    try:
        m = meetings.create_meeting("A-only", workspace_id=ws_a)

        # Workspace B cannot see, fetch, or act on A's meeting.
        assert meetings.list_meetings(workspace_id=ws_b) == []
        with pytest.raises(MeetingNotFound):
            meetings.get_meeting(m.id, workspace_id=ws_b)
        with pytest.raises(MeetingNotFound):
            meetings.transition_status(m.id, meetings.CANCELLED, expected_version=1, workspace_id=ws_b)

        # Workspace A still sees exactly its own.
        assert [x.id for x in meetings.list_meetings(workspace_id=ws_a)] == [m.id]
    finally:
        _cleanup(ws_a, ws_b)


def test_create_meeting_end_before_start_raises_error():
    ws = _new_workspace()
    try:
        with pytest.raises(MeetingValidationError):
            meetings.create_meeting("Invalid Window", workspace_id=ws, scheduled_start=_END, scheduled_end=_START)
    finally:
        _cleanup(ws)


def test_update_meeting_end_before_start_raises_error():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Update Window Test", workspace_id=ws, scheduled_start=_START, scheduled_end=_END)
        with pytest.raises(MeetingValidationError):
            meetings.update_meeting(m.id, expected_version=1, workspace_id=ws, scheduled_end=_START - timedelta(hours=1))
    finally:
        _cleanup(ws)


def test_update_scheduled_meeting_clearing_window_raises_error():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Scheduled Window Clear", workspace_id=ws, scheduled_start=_START, scheduled_end=_END)
        m = meetings.transition_status(m.id, meetings.SCHEDULED, expected_version=1, workspace_id=ws)
        with pytest.raises(MeetingValidationError):
            meetings.update_meeting(m.id, expected_version=m.version, workspace_id=ws, scheduled_start=None)
    finally:
        _cleanup(ws)
