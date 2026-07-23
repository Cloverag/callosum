"""Live-store integration coverage for the P2 Decision aggregate (Meridian, checkpoint 4).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``. These tests
exercise the decision domain against a real Postgres: state machine transitions, director stances,
immutability of approved decisions, supersession version history, optimistic concurrency, and
Row-Level Security tenant isolation across workspaces.
"""

import os
import uuid

import pytest

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip("set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests", allow_module_level=True)

import psycopg

from callosum.config import settings
from meridian import agenda, decisions, meetings
from meridian.decisions import (
    APPROVED,
    DEFERRED,
    PROPOSED,
    REJECTED,
    STANCE_APPROVED,
    STANCE_OPPOSED,
    STANCE_SUPPORTED,
    SUPERSEDED,
    DecisionLockedError,
    DecisionNotFound,
    DecisionValidationError,
    StaleDecisionError,
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
        _admin("DELETE FROM decision_stance WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM decision WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM agenda_item WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM meeting WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM workspace WHERE id = %s", (ws,))


def test_create_and_get_decision():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Decision Meeting", workspace_id=ws)
        ag = agenda.create_agenda_item(m.id, "Pricing Discussion", workspace_id=ws)

        dec = decisions.create_decision(
            m.id,
            "Adopt Pricing Model B",
            workspace_id=ws,
            agenda_item_id=ag.id,
            rationale="Usage-based pricing aligns better with customer value",
        )
        assert dec.meeting_id == m.id
        assert dec.agenda_item_id == ag.id
        assert dec.title == "Adopt Pricing Model B"
        assert dec.rationale == "Usage-based pricing aligns better with customer value"
        assert dec.status == PROPOSED
        assert dec.version == 1
        assert dec.workspace_id == ws
        assert dec.stances == []

        fetched = decisions.get_decision(dec.id, workspace_id=ws)
        assert fetched.id == dec.id
        assert fetched.title == "Adopt Pricing Model B"
    finally:
        _cleanup(ws)


def test_record_stance_and_upsert():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Stance Meeting", workspace_id=ws)
        dec = decisions.create_decision(m.id, "Expand to EU", workspace_id=ws)

        s1 = decisions.record_stance(
            dec.id, "Raj Malhotra", STANCE_SUPPORTED, workspace_id=ws, comment="Huge TAM"
        )
        assert s1.decision_id == dec.id
        assert s1.person_name == "Raj Malhotra"
        assert s1.stance == STANCE_SUPPORTED
        assert s1.comment == "Huge TAM"

        # Record another stance
        decisions.record_stance(dec.id, "Priya Nair", STANCE_OPPOSED, workspace_id=ws, comment="Too early")

        # Update Raj's stance to APPROVED
        s1_updated = decisions.record_stance(
            dec.id, "Raj Malhotra", STANCE_APPROVED, workspace_id=ws, comment="Changed mind after review"
        )
        assert s1_updated.stance == STANCE_APPROVED

        fetched = decisions.get_decision(dec.id, workspace_id=ws)
        assert len(fetched.stances) == 2
        names_and_stances = {(x.person_name, x.stance) for x in fetched.stances}
        assert ("Raj Malhotra", STANCE_APPROVED) in names_and_stances
        assert ("Priya Nair", STANCE_OPPOSED) in names_and_stances
    finally:
        _cleanup(ws)


def test_decision_lifecycle_transitions():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Transition Meeting", workspace_id=ws)
        dec = decisions.create_decision(m.id, "Approve Budget", workspace_id=ws)
        assert dec.status == PROPOSED

        # Transition to APPROVED
        approved_dec = decisions.transition_decision_status(
            dec.id, APPROVED, expected_version=1, workspace_id=ws
        )
        assert approved_dec.status == APPROVED
        assert approved_dec.version == 2
    finally:
        _cleanup(ws)


def test_invalid_transition_raises_validation_error():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Invalid Transition Meeting", workspace_id=ws)
        dec = decisions.create_decision(m.id, "Reject Motion", workspace_id=ws)

        # Move to REJECTED
        dec = decisions.transition_decision_status(dec.id, REJECTED, expected_version=1, workspace_id=ws)
        assert dec.status == REJECTED

        # Transitioning out of REJECTED (terminal for direct transition) is forbidden
        with pytest.raises(DecisionValidationError):
            decisions.transition_decision_status(dec.id, PROPOSED, expected_version=2, workspace_id=ws)
    finally:
        _cleanup(ws)


def test_supersede_approved_decision():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Supersede Meeting", workspace_id=ws)
        old_dec = decisions.create_decision(m.id, "Pricing Flat Rate", workspace_id=ws)
        old_dec = decisions.transition_decision_status(old_dec.id, APPROVED, expected_version=1, workspace_id=ws)

        # Supersede with new decision
        new_dec, updated_old = decisions.supersede_decision(
            old_dec.id,
            "Pricing Model B (Usage Based)",
            expected_version=2,
            workspace_id=ws,
            rationale="Replaces flat rate after Q3 customer feedback",
        )

        assert new_dec.title == "Pricing Model B (Usage Based)"
        assert new_dec.status == PROPOSED
        assert new_dec.version == 1

        assert updated_old.id == old_dec.id
        assert updated_old.status == SUPERSEDED
        assert updated_old.superseded_by_id == new_dec.id
        assert updated_old.version == 3

        # Verify old decision in store retains link to new decision
        fetched_old = decisions.get_decision(old_dec.id, workspace_id=ws)
        assert fetched_old.status == SUPERSEDED
        assert fetched_old.superseded_by_id == new_dec.id
    finally:
        _cleanup(ws)


def test_supersede_non_approved_decision_raises_error():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Supersede Err Meeting", workspace_id=ws)
        dec = decisions.create_decision(m.id, "Draft Decision", workspace_id=ws)

        # Attempting to supersede a PROPOSED decision raises DecisionValidationError
        with pytest.raises(DecisionValidationError):
            decisions.supersede_decision(dec.id, "New Decision", expected_version=1, workspace_id=ws)
    finally:
        _cleanup(ws)


def test_optimistic_concurrency_conflict():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Concurrency Decision Meeting", workspace_id=ws)
        dec = decisions.create_decision(m.id, "Original Title", workspace_id=ws)

        # Writer 1 updates -> version 2
        updated = decisions.update_decision(
            dec.id, expected_version=1, workspace_id=ws, title="Renamed Title"
        )
        assert updated.version == 2

        # Writer 2 holding version 1 is refused
        with pytest.raises(StaleDecisionError):
            decisions.update_decision(dec.id, expected_version=1, workspace_id=ws, title="Stale Title")

        with pytest.raises(StaleDecisionError):
            decisions.transition_decision_status(dec.id, APPROVED, expected_version=1, workspace_id=ws)
    finally:
        _cleanup(ws)


def test_decisions_locked_when_meeting_inactive():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Completed Meeting", workspace_id=ws)
        m = meetings.transition_status(m.id, meetings.CANCELLED, expected_version=1, workspace_id=ws)

        # Creating or modifying decisions on a cancelled/completed meeting raises DecisionLockedError
        with pytest.raises(DecisionLockedError):
            decisions.create_decision(m.id, "Late Decision", workspace_id=ws)
    finally:
        _cleanup(ws)


def test_cross_workspace_isolation():
    ws_a = _new_workspace()
    ws_b = _new_workspace()
    try:
        m_a = meetings.create_meeting("Meeting A", workspace_id=ws_a)
        dec_a = decisions.create_decision(m_a.id, "Secret Decision A", workspace_id=ws_a)
        decisions.record_stance(dec_a.id, "Director A", STANCE_SUPPORTED, workspace_id=ws_a)

        # Workspace B cannot see or modify A's decision or stances
        assert decisions.list_decisions(m_a.id, workspace_id=ws_b) == []

        with pytest.raises(DecisionNotFound):
            decisions.get_decision(dec_a.id, workspace_id=ws_b)

        with pytest.raises(DecisionNotFound):
            decisions.record_stance(dec_a.id, "Hacker", STANCE_OPPOSED, workspace_id=ws_b)

        with pytest.raises(DecisionNotFound):
            decisions.update_decision(dec_a.id, expected_version=1, workspace_id=ws_b, title="Hacked")
    finally:
        _cleanup(ws_a, ws_b)


def test_cascade_delete_on_meeting_deletion():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Cascade Decision Meeting", workspace_id=ws)
        dec = decisions.create_decision(m.id, "Cascading Decision", workspace_id=ws)
        decisions.record_stance(dec.id, "Director X", STANCE_APPROVED, workspace_id=ws)

        # Delete meeting via admin SQL
        _admin("DELETE FROM meeting WHERE id = %s", (uuid.UUID(m.id),))

        # Decision and stance should be deleted via CASCADE
        with pytest.raises(DecisionNotFound):
            decisions.get_decision(dec.id, workspace_id=ws)
    finally:
        _cleanup(ws)


def test_decision_validation_errors():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Validation Meeting", workspace_id=ws)

        # Empty title
        with pytest.raises(DecisionValidationError):
            decisions.create_decision(m.id, "   ", workspace_id=ws)

        dec = decisions.create_decision(m.id, "Valid Title", workspace_id=ws)

        # Empty person name in stance
        with pytest.raises(DecisionValidationError):
            decisions.record_stance(dec.id, "  ", STANCE_SUPPORTED, workspace_id=ws)

        # Invalid stance string
        with pytest.raises(DecisionValidationError):
            decisions.record_stance(dec.id, "Raj", "INVALID_STANCE", workspace_id=ws)

        # Invalid status filter
        with pytest.raises(DecisionValidationError):
            decisions.list_decisions(m.id, workspace_id=ws, status="INVALID_STATUS")

        # No fields to update
        with pytest.raises(DecisionValidationError):
            decisions.update_decision(dec.id, expected_version=1, workspace_id=ws)
    finally:
        _cleanup(ws)
