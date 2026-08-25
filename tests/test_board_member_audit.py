"""The board directory's mutations leave an append-only trail (P4 criterion 1, #166).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

`board_member` was in `audit.AGGREGATE_TYPES` from the start and nothing ever wrote
it, so the four mutating routes changed who sits on the board, who may vote, and who
has departed, with no record that it happened. These pin the four events, the actor,
the payload discipline, and — the part a coverage count cannot show — that a *refused*
write records nothing.
"""

import os
import uuid

import pytest

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip("set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests", allow_module_level=True)

import psycopg

from callosum.config import settings
from meridian import audit, board_members
from meridian.board_members import (
    DIRECTOR,
    NON_VOTING,
    OBSERVER,
    VOTING,
    BoardMemberNotFound,
    StaleBoardMemberError,
)

pytestmark = pytest.mark.integration


def _admin(sql: str, params: tuple = ()) -> None:
    with psycopg.connect(settings().postgres_dsn) as conn:
        conn.execute(sql, params)
        conn.commit()


def _new_workspace() -> str:
    ws = str(uuid.uuid4())
    _admin(
        "INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s)",
        (ws, f"bma-{ws[:8]}", ws),
    )
    return ws


def _cleanup(*workspace_ids: str) -> None:
    for ws in workspace_ids:
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM board_member WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM membership WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM workspace WHERE id = %s", (ws,))


def _events(ws: str, member_id: str | None = None) -> list:
    return audit.list_audit_events(
        aggregate_type="board_member",
        aggregate_id=member_id,
        workspace_id=ws,
    )


def test_creating_a_member_is_audited():
    ws = _new_workspace()
    try:
        m = board_members.create_member("Priya Nair", DIRECTOR, workspace_id=ws)

        events = _events(ws, m.id)
        assert len(events) == 1
        assert events[0].aggregate_type == "board_member"
        assert events[0].action == "created"
        assert str(events[0].aggregate_id) == str(m.id)
        assert events[0].payload["role"] == DIRECTOR
        assert events[0].payload["voting"] == VOTING
        assert events[0].payload["active"] is True
    finally:
        _cleanup(ws)


def test_editing_a_member_records_which_fields_moved():
    """`changed_fields` is the question successive `updated` events cannot otherwise answer."""
    ws = _new_workspace()
    try:
        m = board_members.create_member("Priya Nair", DIRECTOR, workspace_id=ws)
        board_members.update_member(
            m.id, expected_version=m.version, workspace_id=ws, role=OBSERVER, voting=NON_VOTING
        )

        events = _events(ws, m.id)
        # Sorted, not indexed: `list_audit_events` orders by `created_at DESC`, and two
        # events written milliseconds apart can tie on it.
        assert sorted(e.action for e in events) == ["created", "updated"]

        edit = next(e for e in events if e.action == "updated")
        assert set(edit.payload["changed_fields"]) == {"role", "voting"}
        # The payload carries the state *after* the write, so a reader never has to
        # join back to a row that may have moved again since.
        assert edit.payload["role"] == OBSERVER
        assert edit.payload["voting"] == NON_VOTING
    finally:
        _cleanup(ws)


def test_departure_and_return_are_status_changes_not_edits():
    """`status_changed`, matching `commitments.record_update` for the same shape.

    A departure is not a field edit, and the trail has to say which it was: "who was
    on the board on the day of that vote" is answerable from `status_changed` events
    alone, and unanswerable if leaving looks like any other `updated`.
    """
    ws = _new_workspace()
    try:
        m = board_members.create_member("Priya Nair", DIRECTOR, workspace_id=ws)
        left = board_members.deactivate_member(m.id, expected_version=m.version, workspace_id=ws)
        board_members.reactivate_member(m.id, expected_version=left.version, workspace_id=ws)

        actions = [e.action for e in _events(ws, m.id)]
        assert sorted(actions) == ["created", "status_changed", "status_changed"]

        transitions = [e for e in _events(ws, m.id) if e.action == "status_changed"]
        assert {e.payload["active"] for e in transitions} == {True, False}
        assert not any("changed_fields" in e.payload for e in transitions)
    finally:
        _cleanup(ws)


def test_the_actor_is_recorded():
    """Who did this — most of what "audited" means for governance.

    `subject` is a column on `principal_identity`, not `principal`; and `name`, `role`
    and `clearance` are all NOT NULL. The correct two-table form is
    `test_documents_api._principal_with_identity`. Only the `principal` row is needed
    here, because these call the domain directly rather than through a session.
    """
    ws = _new_workspace()
    actor = str(uuid.uuid4())
    _admin(
        "INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, 'director', %s)",
        (actor, f"Audit Actor {actor[:6]}", 4),
    )
    # `record_audit_event` refuses an actor with no active membership in the workspace
    # (`audit.py:188`, ActorNotInWorkspace) — the trail cannot name someone who was not
    # there. A principal row alone is not enough.
    _admin(
        "INSERT INTO membership (principal_id, workspace_id, role, clearance, active)"
        " VALUES (%s, %s, 'director', %s, true)",
        (actor, ws, 4),
    )
    try:
        m = board_members.create_member(
            "Priya Nair", DIRECTOR, workspace_id=ws, actor_principal_id=actor
        )
        board_members.deactivate_member(
            m.id, expected_version=m.version, workspace_id=ws, actor_principal_id=actor
        )

        assert all(str(e.actor_principal_id) == actor for e in _events(ws, m.id))
    finally:
        # `_cleanup` drops audit_event first; the principal can only go after it,
        # because `audit_event.actor_principal_id` is ON DELETE RESTRICT as well.
        _cleanup(ws)
        _admin("DELETE FROM principal WHERE id = %s", (actor,))


def test_contact_email_never_enters_the_trail():
    """The audit table is append-only, so anything written here can never be removed.

    Personal data with no governance meaning must not be in it. This is the assertion
    that fails if someone later 'improves' the payload by dumping the whole row.
    """
    ws = _new_workspace()
    try:
        m = board_members.create_member(
            "Priya Nair", DIRECTOR, workspace_id=ws, contact_email="priya@example.com"
        )
        board_members.update_member(
            m.id, expected_version=m.version, workspace_id=ws, contact_email="new@example.com"
        )

        for e in _events(ws, m.id):
            assert "contact_email" not in e.payload
            assert "example.com" not in str(e.payload)
        # The *fact* that the field was edited is still recorded — only the value is not.
        edit = next(e for e in _events(ws, m.id) if e.action == "updated")
        assert edit.payload["changed_fields"] == ["contact_email"]
    finally:
        _cleanup(ws)


def test_a_refused_write_records_nothing():
    """A stale-version refusal must not leave an event claiming a change happened.

    The audit write is inside the same transaction and *after* the row is confirmed,
    so this is the property that would break first if either moved.
    """
    ws = _new_workspace()
    try:
        m = board_members.create_member("Priya Nair", DIRECTOR, workspace_id=ws)
        before = len(_events(ws, m.id))

        with pytest.raises(StaleBoardMemberError):
            board_members.update_member(
                m.id, expected_version=m.version + 99, workspace_id=ws, role=OBSERVER
            )
        with pytest.raises(BoardMemberNotFound):
            board_members.deactivate_member(
                str(uuid.uuid4()), expected_version=1, workspace_id=ws
            )

        # Neither the refused member nor the workspace as a whole gained an event.
        assert len(_events(ws, m.id)) == before
        assert len(_events(ws)) == before
    finally:
        _cleanup(ws)


def test_the_trail_is_tenant_isolated():
    """A board_member event in one workspace is invisible from another."""
    alpha, beta = _new_workspace(), _new_workspace()
    try:
        m = board_members.create_member("Priya Nair", DIRECTOR, workspace_id=alpha)
        assert len(_events(alpha, m.id)) == 1
        assert _events(beta, m.id) == []
        assert _events(beta) == []
    finally:
        _cleanup(alpha, beta)
