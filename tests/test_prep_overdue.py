"""Readiness and agenda suggestions use the domain's one definition of "overdue" (#238).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest tests/test_prep_overdue.py``.

Both used `status = 'open' AND due_date < NOW()`, where `Commitment.is_overdue` says
open **or in_progress or blocked**, and `due_date < today`. So a blocked, overdue
commitment, the one a board most needs to see, was never counted or suggested, and
work due today was overdue from midnight because `DATE < NOW()` casts the date to
the start of its day.
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
from meridian import board_members, commitments, decisions, meetings, prep

pytestmark = pytest.mark.integration

TODAY = dt.datetime.now(dt.timezone.utc).date()
PAST = TODAY - dt.timedelta(days=3)


def _admin(sql: str, params: tuple = ()) -> None:
    with psycopg.connect(settings().postgres_dsn) as conn:
        conn.execute(sql, params)
        conn.commit()


@pytest.fixture
def board():
    ws, actor = str(uuid.uuid4()), str(uuid.uuid4())
    clearance = identity.ROLE_TO_CLEARANCE["director"]
    _admin("INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s)", (ws, f"od-{ws[:8]}", ws))
    _admin(
        "INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, 'director', %s)",
        (actor, f"Overdue {actor[:6]}", clearance),
    )
    _admin(
        "INSERT INTO membership (principal_id, workspace_id, role, clearance, active)"
        " VALUES (%s, %s, 'director', %s, true)",
        (actor, ws, clearance),
    )
    meeting = meetings.create_meeting("Q4 Board Meeting", workspace_id=ws)
    decision = decisions.create_decision(meeting.id, "Ship pricing B", workspace_id=ws)
    owner = board_members.create_member("Owner", "director", workspace_id=ws, actor_principal_id=actor).id

    def commitment(title, due, *moves):
        c = commitments.create_commitment(decision.id, title, owner, due_date=due, workspace_id=ws)
        for status in moves:
            c = commitments.record_update(c.id, f"-> {status}", expected_version=c.version,
                                          new_status=status, workspace_id=ws)
        return c.id

    ids = {
        "open_past": commitment("Open, past due", PAST),
        "in_progress_past": commitment("In progress, past due", PAST, "in_progress"),
        "blocked_past": commitment("Blocked, past due", PAST, "blocked"),
        "due_today": commitment("Due today", TODAY),
        "completed_past": commitment("Completed, past due", PAST, "in_progress", "completed"),
        "no_date": commitment("No due date", None),
    }
    try:
        yield ws, meeting.id, ids
    finally:
        for table in ("audit_event", "commitment_update", "commitment", "decision",
                      "board_member", "meeting", "membership"):
            _admin(f"DELETE FROM {table} WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM workspace WHERE id = %s", (ws,))
        _admin("DELETE FROM principal WHERE id = %s", (actor,))


EXPECTED = {"open_past", "in_progress_past", "blocked_past"}


def test_readiness_counts_what_is_overdue_agrees_with(board):
    ws, meeting_id, ids = board
    readiness = prep.get_meeting_readiness(meeting_id, workspace_id=ws)
    assert readiness["overdue_commitments_count"] == len(EXPECTED)


def test_agenda_suggestions_name_exactly_the_overdue_commitments(board):
    ws, meeting_id, ids = board
    suggested = {
        s["source"]["id"] for s in prep.get_agenda_suggestions(meeting_id, workspace_id=ws)
        if s["source"]["kind"] == "commitment"
    }
    assert suggested == {ids[k] for k in EXPECTED}


def test_both_agree_with_the_domain_definition(board):
    """The point of #238: one definition. Pinned against `is_overdue` itself."""
    ws, meeting_id, _ = board
    domain = [c for c in commitments.list_commitments(workspace_id=ws) if c.is_overdue(today=TODAY)]
    assert prep.get_meeting_readiness(meeting_id, workspace_id=ws)["overdue_commitments_count"] == len(domain)
