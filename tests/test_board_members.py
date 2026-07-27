"""Live-store integration coverage for the BoardMember directory (Meridian, checkpoint 5a).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``. These
exercise the directory against a real Postgres: the nullable `principal_id`, the
voting enum, deactivate-never-delete, optimistic concurrency, the optional link
from `decision_stance`, and Row-Level Security tenant isolation.
"""

import os
import uuid

import pytest

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip("set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests", allow_module_level=True)

import psycopg

from callosum.config import settings
from meridian import board_members, decisions, meetings
from meridian.board_members import (
    ADVISER,
    DIRECTOR,
    NON_VOTING,
    OBSERVER,
    RECUSED,
    VOTING,
    BoardMemberNotFound,
    BoardMemberValidationError,
    StaleBoardMemberError,
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
        (ws, f"bm-{ws[:8]}", ws),
    )
    return ws


def _cleanup(*workspace_ids: str) -> None:
    for ws in workspace_ids:
        _admin("DELETE FROM decision_stance WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM decision WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM board_member WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM meeting WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM workspace WHERE id = %s", (ws,))


def test_create_and_get_member():
    ws = _new_workspace()
    try:
        m = board_members.create_member(
            "Priya Nair",
            DIRECTOR,
            workspace_id=ws,
            organization="Acme Capital",
            contact_email="priya@example.com",
        )
        assert m.full_name == "Priya Nair"
        assert m.role == DIRECTOR
        assert m.voting == VOTING  # the default
        assert m.active is True
        assert m.version == 1

        assert board_members.get_member(m.id, workspace_id=ws) == m
    finally:
        _cleanup(ws)


def test_member_without_a_login_is_first_class():
    """A director with no `principal` must be recordable, listable and referable.

    This is the headline case for the whole checkpoint. `board_member` exists
    separately from `membership` precisely so that a non-executive director who
    never signs in is still a full participant, so a NULL `principal_id` is the
    normal case and not a degraded one.
    """
    ws = _new_workspace()
    try:
        m = board_members.create_member("Elena Fischer", OBSERVER, workspace_id=ws)
        assert m.principal_id is None

        assert board_members.get_member(m.id, workspace_id=ws).principal_id is None
        assert [x.id for x in board_members.list_members(workspace_id=ws)] == [m.id]
    finally:
        _cleanup(ws)


def test_voting_status_round_trips_and_rejects_unknown_values():
    ws = _new_workspace()
    try:
        for status in (VOTING, NON_VOTING, RECUSED):
            m = board_members.create_member(
                f"Member {status}", DIRECTOR, workspace_id=ws, voting=status
            )
            assert board_members.get_member(m.id, workspace_id=ws).voting == status

        with pytest.raises(BoardMemberValidationError):
            board_members.create_member("Bad", DIRECTOR, workspace_id=ws, voting="abstaining")
        with pytest.raises(BoardMemberValidationError):
            board_members.create_member("Bad", "chairperson", workspace_id=ws)
        with pytest.raises(BoardMemberValidationError):
            board_members.create_member("   ", DIRECTOR, workspace_id=ws)
    finally:
        _cleanup(ws)


def test_list_filters_by_active_and_role():
    ws = _new_workspace()
    try:
        d = board_members.create_member("Alice Director", DIRECTOR, workspace_id=ws)
        a = board_members.create_member("Bob Adviser", ADVISER, workspace_id=ws)
        gone = board_members.create_member("Carol Departed", DIRECTOR, workspace_id=ws)
        board_members.deactivate_member(gone.id, expected_version=1, workspace_id=ws)

        active = board_members.list_members(workspace_id=ws)
        assert {x.id for x in active} == {d.id, a.id}

        assert [x.id for x in board_members.list_members(workspace_id=ws, role=ADVISER)] == [a.id]

        everyone = board_members.list_members(workspace_id=ws, active=None)
        assert {x.id for x in everyone} == {d.id, a.id, gone.id}

        with pytest.raises(BoardMemberValidationError):
            board_members.list_members(workspace_id=ws, role="chairperson")
    finally:
        _cleanup(ws)


def test_deactivated_member_still_resolves_by_id():
    """Departure hides a member from the roster; it must not make them unresolvable.

    Historical stances point at directory entries, so a hard delete would orphan
    records the immutability contract says are permanent. There is no delete
    operation in the module at all — this asserts the consequence.
    """
    ws = _new_workspace()
    try:
        m = board_members.create_member("Marcus Webb", DIRECTOR, workspace_id=ws)
        out = board_members.deactivate_member(m.id, expected_version=1, workspace_id=ws)
        assert out.active is False
        assert out.version == 2

        assert board_members.list_members(workspace_id=ws) == []
        assert board_members.get_member(m.id, workspace_id=ws).full_name == "Marcus Webb"

        back = board_members.reactivate_member(m.id, expected_version=2, workspace_id=ws)
        assert back.active is True
        assert [x.id for x in board_members.list_members(workspace_id=ws)] == [m.id]
    finally:
        _cleanup(ws)


def test_optimistic_concurrency_conflict():
    ws = _new_workspace()
    try:
        m = board_members.create_member("Raj Malhotra", DIRECTOR, workspace_id=ws)
        board_members.update_member(m.id, expected_version=1, workspace_id=ws, organization="Acme")

        with pytest.raises(StaleBoardMemberError):
            board_members.update_member(
                m.id, expected_version=1, workspace_id=ws, organization="Stale"
            )

        with pytest.raises(BoardMemberNotFound):
            board_members.update_member(
                str(uuid.uuid4()), expected_version=1, workspace_id=ws, organization="Ghost"
            )

        with pytest.raises(BoardMemberValidationError):
            board_members.update_member(m.id, expected_version=2, workspace_id=ws)
    finally:
        _cleanup(ws)


def test_update_can_clear_an_optional_field():
    ws = _new_workspace()
    try:
        m = board_members.create_member(
            "Tom Reed", EXECUTIVE_ROLE := "executive", workspace_id=ws, organization="Acme"
        )
        cleared = board_members.update_member(
            m.id, expected_version=1, workspace_id=ws, organization=None
        )
        assert cleared.organization is None
        assert cleared.role == EXECUTIVE_ROLE
    finally:
        _cleanup(ws)


def test_stance_links_to_directory_optionally_and_keeps_the_recorded_name():
    """`board_member_id` resolves a stance; `person_name` records what was minuted.

    They are not redundant. `person_name` is the name as written at the time —
    audit data — while the link answers which directory entry that string refers
    to. A stance with no link is valid and must stay valid, which is why the
    column is nullable forever rather than nullable-for-now.
    """
    ws = _new_workspace()
    try:
        meeting = meetings.create_meeting("Board Meeting", workspace_id=ws)
        d = decisions.create_decision(meeting.id, "Adopt Model B", workspace_id=ws)
        stance = decisions.record_stance(d.id, "R. Malhotra", "SUPPORTED", workspace_id=ws)

        member = board_members.create_member("Raj Malhotra", DIRECTOR, workspace_id=ws)

        # Unlinked is the valid default.
        with psycopg.connect(settings().postgres_dsn) as conn:
            row = conn.execute(
                "SELECT board_member_id FROM decision_stance WHERE id = %s",
                (uuid.UUID(stance.id),),
            ).fetchone()
            assert row[0] is None

            # Linking keeps the recorded spelling intact — that is the point.
            conn.execute(
                "UPDATE decision_stance SET board_member_id = %s WHERE id = %s",
                (uuid.UUID(member.id), uuid.UUID(stance.id)),
            )
            conn.commit()
            name, linked = conn.execute(
                "SELECT person_name, board_member_id FROM decision_stance WHERE id = %s",
                (uuid.UUID(stance.id),),
            ).fetchone()
        assert name == "R. Malhotra"
        assert str(linked) == member.id
    finally:
        _cleanup(ws)


def test_cross_workspace_isolation():
    """A member created in one workspace is invisible from another."""
    wa, wb = _new_workspace(), _new_workspace()
    try:
        m = board_members.create_member("Alpha Director", DIRECTOR, workspace_id=wa)

        assert board_members.list_members(workspace_id=wb) == []
        with pytest.raises(BoardMemberNotFound):
            board_members.get_member(m.id, workspace_id=wb)

        # A write from the wrong workspace must not reach across either.
        with pytest.raises(BoardMemberNotFound):
            board_members.update_member(
                m.id, expected_version=1, workspace_id=wb, organization="Beta Corp"
            )
        assert board_members.get_member(m.id, workspace_id=wa).organization is None
    finally:
        _cleanup(wa, wb)
