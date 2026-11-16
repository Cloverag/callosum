"""Meeting mutations leave an attributed, append-only trail (#168).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest tests/test_meetings_audit.py``.

#168 counted `meetings.py` as 3 of 5 routes unaudited. Traced:

    POST  /api/meetings                  create_meeting     NO audit
    PATCH /api/meetings/{id}             update_meeting     NO audit  <- rescheduling
    POST  /api/meetings/{id}/transition  transition_status  NO audit
    POST/DELETE .../material             assign/unassign    audited and attributed already

The DB-free half is `test_meetings_audit_static.py`.
"""

import datetime as dt
import os
import uuid

import pytest

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip(
        "set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests",
        allow_module_level=True,
    )

import psycopg

from callosum import identity
from callosum.config import settings
from meridian import audit, meetings
from meridian.meetings import InvalidTransition, MeetingNotFound, MeetingValidationError, StaleMeetingError

pytestmark = pytest.mark.integration

START = dt.datetime(2026, 11, 3, 9, 0, tzinfo=dt.timezone.utc)
END = dt.datetime(2026, 11, 3, 11, 0, tzinfo=dt.timezone.utc)


def _admin(sql: str, params: tuple = ()) -> None:
    with psycopg.connect(settings().postgres_dsn) as conn:
        conn.execute(sql, params)
        conn.commit()


class _World:
    def __init__(self) -> None:
        self.ws = str(uuid.uuid4())
        self.actor = str(uuid.uuid4())
        clearance = identity.ROLE_TO_CLEARANCE["director"]
        _admin(
            "INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s)",
            (self.ws, f"mtg-{self.ws[:8]}", self.ws),
        )
        _admin(
            "INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, 'director', %s)",
            (self.actor, f"Mtg Actor {self.actor[:6]}", clearance),
        )
        _admin(
            "INSERT INTO membership (principal_id, workspace_id, role, clearance, active)"
            " VALUES (%s, %s, 'director', %s, true)",
            (self.actor, self.ws, clearance),
        )

    def meeting(self, **kw):
        return meetings.create_meeting(
            "Q4 Board Meeting", workspace_id=self.ws, actor_principal_id=self.actor, **kw
        )

    def events(self, aggregate_id: str | None = None) -> list:
        return audit.list_audit_events(
            aggregate_type="meeting", aggregate_id=aggregate_id, workspace_id=self.ws
        )

    def close(self) -> None:
        for table in ("audit_event", "meeting", "membership"):
            _admin(f"DELETE FROM {table} WHERE workspace_id = %s", (self.ws,))
        _admin("DELETE FROM workspace WHERE id = %s", (self.ws,))
        _admin("DELETE FROM principal WHERE id = %s", (self.actor,))


@pytest.fixture
def w():
    world = _World()
    try:
        yield world
    finally:
        world.close()


def test_create_is_audited_with_the_actor(w):
    m = w.meeting(scheduled_start=START, scheduled_end=END)
    events = w.events(m.id)
    assert [e.action for e in events] == ["created"]
    assert str(events[0].actor_principal_id) == w.actor
    assert events[0].payload["status"] == "draft"
    assert events[0].payload["scheduled_start"] == START.isoformat()


def test_a_rescheduled_meeting_records_when_it_was_before(w):
    m = w.meeting(scheduled_start=START, scheduled_end=END)
    later = START + dt.timedelta(days=7)
    meetings.update_meeting(
        m.id, expected_version=m.version,
        scheduled_start=later, scheduled_end=END + dt.timedelta(days=7),
        workspace_id=w.ws, actor_principal_id=w.actor,
    )
    events = w.events(m.id)
    assert [e.action for e in events] == ["updated", "created"]  # newest first
    p = events[0].payload
    assert str(events[0].actor_principal_id) == w.actor
    assert p["changed_fields"] == ["scheduled_start", "scheduled_end"]
    assert p["from_scheduled_start"] == START.isoformat()
    assert p["scheduled_start"] == later.isoformat()


def test_a_title_edit_carries_no_schedule_history(w):
    m = w.meeting()
    meetings.update_meeting(
        m.id, expected_version=m.version, title="Q4 Board Meeting (rescheduled)",
        workspace_id=w.ws, actor_principal_id=w.actor,
    )
    p = w.events(m.id)[0].payload
    assert p["changed_fields"] == ["title"]
    assert "from_scheduled_start" not in p


def test_a_transition_is_audited_and_names_the_status_it_left(w):
    m = w.meeting(scheduled_start=START, scheduled_end=END)
    meetings.transition_status(
        m.id, meetings.SCHEDULED, expected_version=m.version,
        workspace_id=w.ws, actor_principal_id=w.actor,
    )
    event = w.events(m.id)[0]
    assert event.action == "status_changed"
    assert str(event.actor_principal_id) == w.actor
    assert (event.payload["from_status"], event.payload["status"]) == ("draft", "scheduled")


def test_a_refused_meeting_write_records_nothing(w):
    m = w.meeting()
    before = len(w.events())
    with pytest.raises(MeetingNotFound):
        meetings.update_meeting(
            str(uuid.uuid4()), expected_version=1, title="x",
            workspace_id=w.ws, actor_principal_id=w.actor,
        )
    with pytest.raises(StaleMeetingError):
        meetings.update_meeting(
            m.id, expected_version=m.version + 99, title="x",
            workspace_id=w.ws, actor_principal_id=w.actor,
        )
    with pytest.raises(MeetingValidationError):
        # No time window, so it cannot be scheduled.
        meetings.transition_status(
            m.id, meetings.SCHEDULED, expected_version=m.version,
            workspace_id=w.ws, actor_principal_id=w.actor,
        )
    with pytest.raises(InvalidTransition):
        meetings.transition_status(
            m.id, meetings.COMPLETED, expected_version=m.version,
            workspace_id=w.ws, actor_principal_id=w.actor,
        )
    assert len(w.events()) == before


def test_an_actor_outside_the_workspace_rolls_the_whole_mutation_back(w):
    outsider = str(uuid.uuid4())
    _admin(
        "INSERT INTO principal (id, name, role, clearance) VALUES (%s, 'Outsider', 'observer', 0)",
        (outsider,),
    )
    try:
        with pytest.raises(audit.ActorNotInWorkspace):
            meetings.create_meeting("Should not survive", workspace_id=w.ws, actor_principal_id=outsider)
        assert meetings.list_meetings(workspace_id=w.ws) == []
        assert w.events() == []
    finally:
        _admin("DELETE FROM principal WHERE id = %s", (outsider,))
