"""Decision mutations leave an attributed, append-only trail (#168).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest tests/test_decisions_audit.py``.

#168 counted `decisions.py` as 4 of 5 routes unaudited. Traced:

    POST  /api/decisions                  create_decision             NO audit
    PATCH /api/decisions/{id}             update_decision             NO audit
    POST  /api/decisions/{id}/stance      record_stance               audited, ANONYMOUS
    POST  /api/decisions/{id}/transition  transition_decision_status  NO audit  <- approval
    POST  /api/decisions/{id}/supersede   supersede_decision          NO audit

`record_stance`'s `person_name` is whose stance it is, typed by the caller; it says
nothing about who recorded it. The DB-free half is `test_decisions_audit_static.py`.
"""

import json
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
from meridian import audit, decisions, meetings
from meridian.decisions import (
    DecisionLockedError,
    DecisionNotFound,
    DecisionValidationError,
    StaleDecisionError,
)

pytestmark = pytest.mark.integration


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
            (self.ws, f"dec-{self.ws[:8]}", self.ws),
        )
        _admin(
            "INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, 'director', %s)",
            (self.actor, f"Dec Actor {self.actor[:6]}", clearance),
        )
        _admin(
            "INSERT INTO membership (principal_id, workspace_id, role, clearance, active)"
            " VALUES (%s, %s, 'director', %s, true)",
            (self.actor, self.ws, clearance),
        )
        self.meeting = meetings.create_meeting("Audited Board Meeting", workspace_id=self.ws)

    def decision(self, title: str = "Adopt pricing B", rationale: str | None = None):
        return decisions.create_decision(
            self.meeting.id, title, rationale=rationale,
            workspace_id=self.ws, actor_principal_id=self.actor,
        )

    def approve(self, d):
        return decisions.transition_decision_status(
            d.id, decisions.APPROVED, expected_version=d.version,
            workspace_id=self.ws, actor_principal_id=self.actor,
        )

    def events(self, aggregate_id: str | None = None) -> list:
        return audit.list_audit_events(
            aggregate_type="decision", aggregate_id=aggregate_id, workspace_id=self.ws
        )

    def close(self) -> None:
        for table in ("audit_event", "decision_stance", "decision", "agenda_item",
                      "meeting", "membership"):
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


def _newest_first(events) -> list[str]:
    """`list_audit_events` is `ORDER BY created_at DESC, id DESC`."""
    return [e.action for e in events]


def test_create_is_audited_with_the_actor(w):
    d = w.decision()
    events = w.events(d.id)
    assert _newest_first(events) == ["created"]
    assert str(events[0].actor_principal_id) == w.actor
    assert events[0].payload["status"] == "proposed"
    assert events[0].payload["meeting_id"] == w.meeting.id


def test_update_names_only_the_fields_the_caller_supplied(w):
    d = w.decision()
    decisions.update_decision(
        d.id, expected_version=d.version, title="Adopt pricing B (revised)",
        workspace_id=w.ws, actor_principal_id=w.actor,
    )
    events = w.events(d.id)
    assert _newest_first(events) == ["updated", "created"]
    assert str(events[0].actor_principal_id) == w.actor
    assert events[0].payload["changed_fields"] == ["title"]


def test_approval_is_audited_and_names_the_status_it_left(w):
    """The mutation that matters most here, and it wrote nothing."""
    approved = w.approve(w.decision())
    event = w.events(approved.id)[0]
    assert event.action == "status_changed"
    assert str(event.actor_principal_id) == w.actor
    assert event.payload["status"] == "approved"
    assert event.payload["from_status"] == "proposed"


def test_supersede_is_one_event_on_the_old_decision(w):
    approved = w.approve(w.decision())
    new, old = decisions.supersede_decision(
        approved.id, "Adopt pricing C", expected_version=approved.version,
        workspace_id=w.ws, actor_principal_id=w.actor,
    )
    old_events = w.events(old.id)
    assert _newest_first(old_events) == ["superseded", "status_changed", "created"]
    assert old_events[0].payload["new_decision_id"] == new.id
    assert str(old_events[0].actor_principal_id) == w.actor
    assert w.events(new.id) == []


def test_a_stance_now_names_the_caller_as_well_as_the_person(w):
    d = w.decision()
    decisions.record_stance(
        d.id, "Priya Nair", "SUPPORTED",
        workspace_id=w.ws, actor_principal_id=w.actor,
    )
    event = w.events(d.id)[0]
    assert event.action == "voted"
    assert str(event.actor_principal_id) == w.actor
    # Payload shape unchanged, so old and new events for the same act agree.
    assert event.payload == {"person_name": "Priya Nair", "old_stance": None, "new_stance": "SUPPORTED"}


def test_a_refused_decision_write_records_nothing(w):
    d = w.decision()
    before = len(w.events())

    with pytest.raises(DecisionNotFound):
        decisions.update_decision(
            str(uuid.uuid4()), expected_version=1, title="x",
            workspace_id=w.ws, actor_principal_id=w.actor,
        )
    with pytest.raises(StaleDecisionError):
        decisions.transition_decision_status(
            d.id, decisions.APPROVED, expected_version=d.version + 99,
            workspace_id=w.ws, actor_principal_id=w.actor,
        )
    with pytest.raises(DecisionValidationError):
        # Only an approved decision may be superseded.
        decisions.supersede_decision(
            d.id, "Too early", expected_version=d.version,
            workspace_id=w.ws, actor_principal_id=w.actor,
        )
    assert len(w.events()) == before

    approved = w.approve(d)
    with pytest.raises(DecisionLockedError):
        decisions.update_decision(
            approved.id, expected_version=approved.version, title="too late",
            workspace_id=w.ws, actor_principal_id=w.actor,
        )
    with pytest.raises(DecisionLockedError):
        decisions.record_stance(
            approved.id, "Priya Nair", "OPPOSED",
            workspace_id=w.ws, actor_principal_id=w.actor,
        )
    assert len(w.events()) == before + 1


def test_an_actor_outside_the_workspace_rolls_the_whole_mutation_back(w):
    outsider = str(uuid.uuid4())
    _admin(
        "INSERT INTO principal (id, name, role, clearance) VALUES (%s, 'Outsider', 'observer', 0)",
        (outsider,),
    )
    try:
        with pytest.raises(audit.ActorNotInWorkspace):
            decisions.create_decision(
                w.meeting.id, "Should not survive",
                workspace_id=w.ws, actor_principal_id=outsider,
            )
        assert decisions.list_decisions(w.meeting.id, workspace_id=w.ws) == []
        assert w.events() == []
    finally:
        _admin("DELETE FROM principal WHERE id = %s", (outsider,))


def test_the_payload_never_carries_the_rationale(w):
    secret = "Because the CFO's 185K retention package depends on it."
    d = w.decision(rationale=secret)
    decisions.update_decision(
        d.id, expected_version=d.version, rationale=secret + " Revised.",
        workspace_id=w.ws, actor_principal_id=w.actor,
    )
    for event in w.events(d.id):
        assert "185K" not in json.dumps(event.payload)
    assert w.events(d.id)[-1].payload["rationale_chars"] == len(secret)
