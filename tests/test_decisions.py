"""Live-store integration coverage for the P2 Decision aggregate (Meridian, checkpoint 4).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``. These tests
exercise the decision domain against a real Postgres: state machine transitions, director stances,
immutability of approved decisions, supersession version history, optimistic concurrency, and
Row-Level Security tenant isolation across workspaces.
"""

from datetime import datetime, timedelta, timezone
import os
import uuid

import pytest

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip("set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests", allow_module_level=True)

import psycopg

from callosum.config import settings
from meridian import agenda, audit, decisions, meetings
from meridian.decisions import (
    APPROVED,
    DEFERRED,
    PROPOSED,
    REJECTED,
    STANCE_APPROVED,
    STANCE_OPPOSED,
    STANCE_REQUESTED,
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
        # Before the aggregates: `record_stance` now writes an audit_event in the same
        # transaction, and the workspace row cannot go while those rows reference it.
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
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


def test_record_stance_writes_an_audit_event_carrying_the_previous_stance():
    """The audit trail must show what a stance changed *from*, not only its new value.

    Written this way on purpose: the first stance and the change to it are asserted
    separately, because the interesting field is `old_stance` and it only exists on the
    second. A test that recorded one stance and checked an event existed would pass
    against an implementation that read the prior row *after* the upsert had already
    overwritten it — which is the bug this ordering avoids.
    """
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Audited Stance Meeting", workspace_id=ws)
        dec = decisions.create_decision(m.id, "Adopt the new auditor", workspace_id=ws)

        decisions.record_stance(dec.id, "Raj Malhotra", STANCE_SUPPORTED, workspace_id=ws)
        decisions.record_stance(dec.id, "Raj Malhotra", STANCE_OPPOSED, workspace_id=ws)

        events = audit.list_audit_events(
            aggregate_type="decision", aggregate_id=dec.id, action="voted", workspace_id=ws
        )
        assert len(events) == 2, f"expected one event per stance write, got {len(events)}"

        by_new_stance = {e.payload["new_stance"]: e.payload for e in events}

        # First stance: nothing to have changed from.
        assert by_new_stance[STANCE_SUPPORTED]["old_stance"] is None
        assert by_new_stance[STANCE_SUPPORTED]["person_name"] == "Raj Malhotra"

        # The change carries both ends of it.
        assert by_new_stance[STANCE_OPPOSED]["old_stance"] == STANCE_SUPPORTED
    finally:
        _cleanup(ws)


def test_a_failed_stance_audit_write_rolls_back_the_stance(monkeypatch):
    """The audit event and the stance commit together or not at all.

    `record_audit_event` documents that it must run inside the mutation's transaction,
    and `store.pg` rolls back on any exception. This pins the consequence: an audit
    write that fails must not leave a stance behind. The rejected alternative in the
    original patch wrapped the audit call in `except Exception: pass`, which keeps the
    stance and silently drops its record — the one outcome an append-only trail exists
    to prevent.

    Forced with monkeypatch because no ordinary input makes the call fail once the
    aggregate_type and action validate.
    """
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Rollback Meeting", workspace_id=ws)
        dec = decisions.create_decision(m.id, "Approve the budget", workspace_id=ws)

        def _fail(*args, **kwargs):
            raise RuntimeError("audit unavailable")

        monkeypatch.setattr(audit, "record_audit_event", _fail)

        with pytest.raises(RuntimeError, match="audit unavailable"):
            decisions.record_stance(dec.id, "Priya Nair", STANCE_SUPPORTED, workspace_id=ws)

        monkeypatch.undo()

        fetched = decisions.get_decision(dec.id, workspace_id=ws)
        assert fetched.stances == [], "the stance survived an audit write that failed"
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


def test_mismatched_agenda_item_meeting_raises_validation_error():
    ws = _new_workspace()
    try:
        m1 = meetings.create_meeting("Meeting 1", workspace_id=ws)
        m2 = meetings.create_meeting("Meeting 2", workspace_id=ws)
        ag2 = agenda.create_agenda_item(m2.id, "Meeting 2 Agenda Item", workspace_id=ws)

        # Attaching m2's agenda item to a decision under m1 raises DecisionValidationError
        with pytest.raises(DecisionValidationError):
            decisions.create_decision(m1.id, "Mismatched Decision", workspace_id=ws, agenda_item_id=ag2.id)
    finally:
        _cleanup(ws)


def test_list_decisions_status_filtering():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Filter Meeting", workspace_id=ws)
        d1 = decisions.create_decision(m.id, "Decision 1", workspace_id=ws)
        d2 = decisions.create_decision(m.id, "Decision 2", workspace_id=ws)
        d3 = decisions.create_decision(m.id, "Decision 3", workspace_id=ws)

        d2 = decisions.transition_decision_status(d2.id, APPROVED, expected_version=1, workspace_id=ws)
        d3 = decisions.transition_decision_status(d3.id, REJECTED, expected_version=1, workspace_id=ws)

        proposed_list = decisions.list_decisions(m.id, workspace_id=ws, status=PROPOSED)
        assert [x.id for x in proposed_list] == [d1.id]

        approved_list = decisions.list_decisions(m.id, workspace_id=ws, status=APPROVED)
        assert [x.id for x in approved_list] == [d2.id]

        rejected_list = decisions.list_decisions(m.id, workspace_id=ws, status=REJECTED)
        assert [x.id for x in rejected_list] == [d3.id]

        all_list = decisions.list_decisions(m.id, workspace_id=ws)
        assert len(all_list) == 3
    finally:
        _cleanup(ws)


def test_transition_to_deferred_and_terminal_guard():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Deferred Meeting", workspace_id=ws)
        dec = decisions.create_decision(m.id, "Table Motion", workspace_id=ws)

        deferred_dec = decisions.transition_decision_status(
            dec.id, DEFERRED, expected_version=1, workspace_id=ws
        )
        assert deferred_dec.status == DEFERRED

        # Cannot directly transition out of DEFERRED
        with pytest.raises(DecisionValidationError):
            decisions.transition_decision_status(
                dec.id, APPROVED, expected_version=2, workspace_id=ws
            )
    finally:
        _cleanup(ws)


def test_update_rationale_clearing_and_modification():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Rationale Meeting", workspace_id=ws)
        dec = decisions.create_decision(
            m.id, "Rationale Test", rationale="Initial Rationale", workspace_id=ws
        )
        assert dec.rationale == "Initial Rationale"

        # Update rationale
        updated = decisions.update_decision(
            dec.id, expected_version=1, workspace_id=ws, rationale="New Rationale"
        )
        assert updated.rationale == "New Rationale"

        # Clear rationale (setting to None)
        cleared = decisions.update_decision(
            dec.id, expected_version=2, workspace_id=ws, rationale=None
        )
        assert cleared.rationale is None
    finally:
        _cleanup(ws)


def test_multi_director_stance_aggregation():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Multi Stance Meeting", workspace_id=ws)
        d1 = decisions.create_decision(m.id, "Dec 1", workspace_id=ws)
        d2 = decisions.create_decision(m.id, "Dec 2", workspace_id=ws)

        directors = [
            ("Alice", STANCE_SUPPORTED),
            ("Bob", STANCE_OPPOSED),
            ("Charlie", STANCE_APPROVED),
            ("Diana", STANCE_REQUESTED),
            ("Eve", STANCE_SUPPORTED),
        ]
        for name, st in directors:
            decisions.record_stance(d1.id, name, st, workspace_id=ws)

        decisions.record_stance(d2.id, "Frank", STANCE_SUPPORTED, workspace_id=ws)

        fetched_d1 = decisions.get_decision(d1.id, workspace_id=ws)
        assert len(fetched_d1.stances) == 5
        assert [x.person_name for x in fetched_d1.stances] == ["Alice", "Bob", "Charlie", "Diana", "Eve"]

        all_decs = decisions.list_decisions(m.id, workspace_id=ws)
        assert len(all_decs[0].stances) == 5
        assert len(all_decs[1].stances) == 1
    finally:
        _cleanup(ws)


def test_chained_supersession_history():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Chained Supersession Meeting", workspace_id=ws)

        # 1. Decision v1 (Flat Rate) -> Approved
        v1 = decisions.create_decision(m.id, "Pricing v1 (Flat Rate)", workspace_id=ws)
        v1 = decisions.transition_decision_status(v1.id, APPROVED, expected_version=1, workspace_id=ws)

        # 2. Decision v2 (Tiered Rate) supersedes v1 -> Approved
        v2, v1_updated = decisions.supersede_decision(
            v1.id, "Pricing v2 (Tiered Rate)", expected_version=2, workspace_id=ws
        )
        v2 = decisions.transition_decision_status(v2.id, APPROVED, expected_version=1, workspace_id=ws)

        # 3. Decision v3 (Usage Based) supersedes v2 -> Proposed
        v3, v2_updated = decisions.supersede_decision(
            v2.id, "Pricing v3 (Usage Based)", expected_version=2, workspace_id=ws
        )

        assert v1_updated.status == SUPERSEDED
        assert v1_updated.superseded_by_id == v2.id

        assert v2_updated.status == SUPERSEDED
        assert v2_updated.superseded_by_id == v3.id

        assert v3.status == PROPOSED
        assert v3.superseded_by_id is None

        # Verify full chain in database
        f1 = decisions.get_decision(v1.id, workspace_id=ws)
        f2 = decisions.get_decision(v2.id, workspace_id=ws)
        f3 = decisions.get_decision(v3.id, workspace_id=ws)

        assert f1.superseded_by_id == f2.id
        assert f2.superseded_by_id == f3.id
        assert f3.superseded_by_id is None
    finally:
        _cleanup(ws)


def test_create_decision_during_in_progress_meeting():
    ws = _new_workspace()
    try:
        now_dt = datetime.now(timezone.utc)
        m = meetings.create_meeting(
            "Live Meeting",
            scheduled_start=now_dt,
            scheduled_end=now_dt + timedelta(hours=1),
            workspace_id=ws,
        )
        m = meetings.transition_status(m.id, meetings.SCHEDULED, expected_version=1, workspace_id=ws)
        m = meetings.transition_status(m.id, meetings.IN_PROGRESS, expected_version=2, workspace_id=ws)

        # Decisions can be recorded during an IN_PROGRESS meeting
        dec = decisions.create_decision(m.id, "Live Decision", workspace_id=ws)
        assert dec.status == PROPOSED
        assert dec.meeting_id == m.id
    finally:
        _cleanup(ws)


def test_record_stance_on_non_proposed_decision_raises_locked_error():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Approved Stance Meeting", workspace_id=ws)
        dec = decisions.create_decision(m.id, "Immutable Decision", workspace_id=ws)
        dec = decisions.transition_decision_status(dec.id, APPROVED, expected_version=1, workspace_id=ws)

        # Recording stance on an APPROVED decision must raise DecisionLockedError
        with pytest.raises(DecisionLockedError):
            decisions.record_stance(dec.id, "Late Director", STANCE_SUPPORTED, workspace_id=ws)
    finally:
        _cleanup(ws)


def test_record_stance_upsert_preserves_created_at_and_updates_updated_at():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Stance Timestamp Meeting", workspace_id=ws)
        dec = decisions.create_decision(m.id, "Stance Timestamp Decision", workspace_id=ws)

        s1 = decisions.record_stance(dec.id, "Director Timestamp", STANCE_SUPPORTED, workspace_id=ws)
        initial_created_at = s1.created_at
        initial_updated_at = s1.updated_at

        # Upsert stance with new comment
        s2 = decisions.record_stance(
            dec.id, "Director Timestamp", STANCE_APPROVED, workspace_id=ws, comment="Changed to approved"
        )

        assert s2.created_at == initial_created_at
        assert s2.updated_at > initial_updated_at
        assert s2.stance == STANCE_APPROVED
        assert s2.comment == "Changed to approved"
    finally:
        _cleanup(ws)
