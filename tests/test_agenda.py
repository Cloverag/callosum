"""Live-store integration coverage for the P2 AgendaItem aggregate (Meridian, checkpoint 2).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``. These tests
exercise the agenda domain against a real Postgres: position contiguity, shifting on
insert/delete, atomic reordering, meeting-lifecycle lock enforcement, optimistic concurrency,
and Row-Level Security tenant isolation across workspaces.
"""

import os
import uuid

import pytest

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip("set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests", allow_module_level=True)

import psycopg

from callosum.config import settings
from meridian import agenda, meetings
from meridian.agenda import (
    AgendaItemNotFound,
    AgendaItemValidationError,
    AgendaLockedError,
    StaleAgendaItemError,
)
from meridian.meetings import MeetingNotFound

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
        _admin("DELETE FROM agenda_item WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM meeting WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM workspace WHERE id = %s", (ws,))


def test_create_and_get_agenda_item():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Agenda Test Meeting", workspace_id=ws)
        item = agenda.create_agenda_item(
            m.id,
            "Financial Review",
            workspace_id=ws,
            description="Review Q2 burn and ARR",
            duration_minutes=30,
            presenter="CFO",
        )
        assert item.meeting_id == m.id
        assert item.title == "Financial Review"
        assert item.description == "Review Q2 burn and ARR"
        assert item.duration_minutes == 30
        assert item.presenter == "CFO"
        assert item.position == 1
        assert item.version == 1
        assert item.workspace_id == ws

        fetched = agenda.get_agenda_item(item.id, workspace_id=ws)
        assert fetched.id == item.id
        assert fetched.title == "Financial Review"
    finally:
        _cleanup(ws)


def test_auto_positioning():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Auto Pos Meeting", workspace_id=ws)
        i1 = agenda.create_agenda_item(m.id, "Item 1", workspace_id=ws)
        i2 = agenda.create_agenda_item(m.id, "Item 2", workspace_id=ws)
        i3 = agenda.create_agenda_item(m.id, "Item 3", workspace_id=ws)

        assert (i1.position, i2.position, i3.position) == (1, 2, 3)

        items = agenda.list_agenda_items(m.id, workspace_id=ws)
        assert [x.title for x in items] == ["Item 1", "Item 2", "Item 3"]
        assert [x.position for x in items] == [1, 2, 3]
    finally:
        _cleanup(ws)


def test_explicit_position_insert_and_shift():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Shift Meeting", workspace_id=ws)
        i1 = agenda.create_agenda_item(m.id, "First", workspace_id=ws)
        i2 = agenda.create_agenda_item(m.id, "Second", workspace_id=ws)
        assert (i1.position, i2.position) == (1, 2)

        inserted = agenda.create_agenda_item(m.id, "Top Priority", position=1, workspace_id=ws)
        assert inserted.position == 1

        items = agenda.list_agenda_items(m.id, workspace_id=ws)
        assert [x.title for x in items] == ["Top Priority", "First", "Second"]
        assert [x.position for x in items] == [1, 2, 3]
    finally:
        _cleanup(ws)


def test_delete_agenda_item_shifts_positions():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Delete Shift Meeting", workspace_id=ws)
        i1 = agenda.create_agenda_item(m.id, "Item A", workspace_id=ws)
        i2 = agenda.create_agenda_item(m.id, "Item B", workspace_id=ws)
        i3 = agenda.create_agenda_item(m.id, "Item C", workspace_id=ws)

        agenda.delete_agenda_item(i2.id, expected_version=1, workspace_id=ws)

        items = agenda.list_agenda_items(m.id, workspace_id=ws)
        assert len(items) == 2
        assert [x.title for x in items] == ["Item A", "Item C"]
        assert [x.position for x in items] == [1, 2]
    finally:
        _cleanup(ws)


def test_atomic_reordering():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Reorder Meeting", workspace_id=ws)
        i1 = agenda.create_agenda_item(m.id, "One", workspace_id=ws)
        i2 = agenda.create_agenda_item(m.id, "Two", workspace_id=ws)
        i3 = agenda.create_agenda_item(m.id, "Three", workspace_id=ws)

        reordered = agenda.reorder_agenda_items(m.id, [i3.id, i1.id, i2.id], workspace_id=ws)
        assert [x.title for x in reordered] == ["Three", "One", "Two"]
        assert [x.position for x in reordered] == [1, 2, 3]
    finally:
        _cleanup(ws)


def test_agenda_locked_when_meeting_not_mutable():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting(
            "Locked Meeting",
            workspace_id=ws,
            scheduled_start=meetings.datetime(2026, 8, 1, 14, 0, tzinfo=meetings.timezone.utc),
            scheduled_end=meetings.datetime(2026, 8, 1, 15, 0, tzinfo=meetings.timezone.utc),
        )
        i1 = agenda.create_agenda_item(m.id, "Pre-lock item", workspace_id=ws)

        m = meetings.transition_status(m.id, meetings.SCHEDULED, expected_version=1, workspace_id=ws)
        m = meetings.transition_status(m.id, meetings.IN_PROGRESS, expected_version=2, workspace_id=ws)

        with pytest.raises(AgendaLockedError):
            agenda.create_agenda_item(m.id, "Late addition", workspace_id=ws)

        with pytest.raises(AgendaLockedError):
            agenda.update_agenda_item(i1.id, expected_version=1, workspace_id=ws, title="Renamed")

        with pytest.raises(AgendaLockedError):
            agenda.delete_agenda_item(i1.id, expected_version=1, workspace_id=ws)

        with pytest.raises(AgendaLockedError):
            agenda.reorder_agenda_items(m.id, [i1.id], workspace_id=ws)
    finally:
        _cleanup(ws)


def test_optimistic_concurrency():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Concurrency Meeting", workspace_id=ws)
        item = agenda.create_agenda_item(m.id, "Original", workspace_id=ws)

        updated = agenda.update_agenda_item(item.id, expected_version=1, workspace_id=ws, title="Updated")
        assert updated.version == 2

        with pytest.raises(StaleAgendaItemError):
            agenda.update_agenda_item(item.id, expected_version=1, workspace_id=ws, title="Stale Update")

        with pytest.raises(StaleAgendaItemError):
            agenda.delete_agenda_item(item.id, expected_version=1, workspace_id=ws)
    finally:
        _cleanup(ws)


def test_cross_workspace_isolation():
    ws_a = _new_workspace()
    ws_b = _new_workspace()
    try:
        m_a = meetings.create_meeting("Meeting A", workspace_id=ws_a)
        item_a = agenda.create_agenda_item(m_a.id, "Secret Agenda A", workspace_id=ws_a)

        assert agenda.list_agenda_items(m_a.id, workspace_id=ws_b) == []

        with pytest.raises(AgendaItemNotFound):
            agenda.get_agenda_item(item_a.id, workspace_id=ws_b)

        with pytest.raises(AgendaItemNotFound):
            agenda.update_agenda_item(item_a.id, expected_version=1, workspace_id=ws_b, title="Hacked")

        with pytest.raises(AgendaItemNotFound):
            agenda.delete_agenda_item(item_a.id, expected_version=1, workspace_id=ws_b)
    finally:
        _cleanup(ws_a, ws_b)


def test_cascade_delete_on_meeting_deletion():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Cascade Meeting", workspace_id=ws)
        item = agenda.create_agenda_item(m.id, "Cascaded Item", workspace_id=ws)

        _admin("DELETE FROM meeting WHERE id = %s", (uuid.UUID(m.id),))

        with pytest.raises(AgendaItemNotFound):
            agenda.get_agenda_item(item.id, workspace_id=ws)
    finally:
        _cleanup(ws)


def test_out_of_bounds_position_clamping():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Clamp Meeting", workspace_id=ws)
        i1 = agenda.create_agenda_item(m.id, "First", workspace_id=ws)
        i2 = agenda.create_agenda_item(m.id, "Second", workspace_id=ws)

        # Explicit position=99 should be clamped to 3
        clamped = agenda.create_agenda_item(m.id, "Far Out", position=99, workspace_id=ws)
        assert clamped.position == 3

        items = agenda.list_agenda_items(m.id, workspace_id=ws)
        assert [x.position for x in items] == [1, 2, 3]
    finally:
        _cleanup(ws)


def test_empty_title_validation():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Title Test", workspace_id=ws)
        with pytest.raises(AgendaItemValidationError):
            agenda.create_agenda_item(m.id, "   ", workspace_id=ws)

        item = agenda.create_agenda_item(m.id, "Valid", workspace_id=ws)
        with pytest.raises(AgendaItemValidationError):
            agenda.update_agenda_item(item.id, expected_version=1, workspace_id=ws, title="")
    finally:
        _cleanup(ws)


def test_invalid_duration_validation():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Duration Test", workspace_id=ws)
        with pytest.raises(AgendaItemValidationError):
            agenda.create_agenda_item(m.id, "Item", duration_minutes=0, workspace_id=ws)

        with pytest.raises(AgendaItemValidationError):
            agenda.create_agenda_item(m.id, "Item", duration_minutes="invalid", workspace_id=ws)
    finally:
        _cleanup(ws)


def test_reorder_incomplete_item_list_validation():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Reorder Val Meeting", workspace_id=ws)
        i1 = agenda.create_agenda_item(m.id, "One", workspace_id=ws)
        i2 = agenda.create_agenda_item(m.id, "Two", workspace_id=ws)

        # Missing i2 -> raises AgendaItemValidationError
        with pytest.raises(AgendaItemValidationError):
            agenda.reorder_agenda_items(m.id, [i1.id], workspace_id=ws)
    finally:
        _cleanup(ws)


def test_reorder_empty_list_validation():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Reorder Empty Meeting", workspace_id=ws)
        with pytest.raises(AgendaItemValidationError):
            agenda.reorder_agenda_items(m.id, [], workspace_id=ws)
    finally:
        _cleanup(ws)


def test_negative_or_zero_position_validation():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Zero Position Test", workspace_id=ws)
        with pytest.raises(AgendaItemValidationError):
            agenda.create_agenda_item(m.id, "Zero Pos", position=0, workspace_id=ws)
        with pytest.raises(AgendaItemValidationError):
            agenda.create_agenda_item(m.id, "Negative Pos", position=-5, workspace_id=ws)
    finally:
        _cleanup(ws)


def test_update_agenda_item_no_fields_raises_validation_error():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("No Field Update Test", workspace_id=ws)
        item = agenda.create_agenda_item(m.id, "Item 1", workspace_id=ws)
        with pytest.raises(AgendaItemValidationError):
            agenda.update_agenda_item(item.id, expected_version=1, workspace_id=ws)
    finally:
        _cleanup(ws)


def test_reorder_duplicate_ids_validation():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Duplicate Reorder Test", workspace_id=ws)
        i1 = agenda.create_agenda_item(m.id, "Item 1", workspace_id=ws)
        with pytest.raises(AgendaItemValidationError):
            agenda.reorder_agenda_items(m.id, [i1.id, i1.id], workspace_id=ws)
    finally:
        _cleanup(ws)


def test_create_agenda_item_nonexistent_meeting_raises_not_found():
    ws = _new_workspace()
    try:
        fake_id = str(uuid.uuid4())
        with pytest.raises(MeetingNotFound):
            agenda.create_agenda_item(fake_id, "Ghost Item", workspace_id=ws)
    finally:
        _cleanup(ws)


def test_update_and_delete_nonexistent_agenda_item_raises_not_found():
    ws = _new_workspace()
    try:
        fake_id = str(uuid.uuid4())
        with pytest.raises(AgendaItemNotFound):
            agenda.update_agenda_item(fake_id, expected_version=1, workspace_id=ws, title="Ghost")

        with pytest.raises(AgendaItemNotFound):
            agenda.delete_agenda_item(fake_id, expected_version=1, workspace_id=ws)
    finally:
        _cleanup(ws)
