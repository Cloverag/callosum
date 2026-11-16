"""Commitment mutations leave an attributed, append-only trail (#168).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest tests/test_commitments_audit.py``.

---------------------------------------------------------------------------
THE GAP
---------------------------------------------------------------------------
#168 counted `commitments.py` as 2 of 3 routes unaudited. Tracing each route:

    POST  /api/commitments               create_commitment   NO audit
    PATCH /api/commitments/{id}          update_commitment   NO audit
    POST  /api/commitments/{id}/updates  record_update       audited, but ANONYMOUS

The PATCH is the one that matters. It is how a commitment's **owner is reassigned and
its deadline moved** — the two facts FR-EXEC-01 exists to hold someone to — and it left
no trace at all. The one event that did exist named no caller; its
`author_board_member_id` is a value the client supplies in the request body, so it
records whom an update is attributed *to*, not who submitted it.

`record_delivery_attempt` is the fourth writer and is deliberately not audited here: it
has no route, and delivery is inert until P8
(`test_d2c_write_api.py::test_there_is_no_delivery_endpoint`). Its exemption is named in
`test_commitments_audit_static.py` rather than tolerated silently.

The DB-free half is `tests/test_commitments_audit_static.py`.
"""

import datetime as dt
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
from meridian import audit, board_members, commitments, decisions, meetings, resolutions
from meridian.commitments import (
    BoardMemberNotFound,
    CommitmentLockedError,
    CommitmentNotFound,
    DecisionNotFound,
    StaleCommitmentError,
)

pytestmark = pytest.mark.integration


def _admin(sql: str, params: tuple = ()) -> None:
    with psycopg.connect(settings().postgres_dsn) as conn:
        conn.execute(sql, params)
        conn.commit()


class _World:
    """A workspace, an actor with an active membership, a decision and two owners."""

    def __init__(self) -> None:
        self.ws = str(uuid.uuid4())
        self.actor = str(uuid.uuid4())
        clearance = identity.ROLE_TO_CLEARANCE["director"]
        _admin(
            "INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s)",
            (self.ws, f"com-{self.ws[:8]}", self.ws),
        )
        _admin(
            "INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, 'director', %s)",
            (self.actor, f"Com Actor {self.actor[:6]}", clearance),
        )
        _admin(
            "INSERT INTO membership (principal_id, workspace_id, role, clearance, active)"
            " VALUES (%s, %s, 'director', %s, true)",
            (self.actor, self.ws, clearance),
        )
        self.meeting = meetings.create_meeting("Audited Board Meeting", workspace_id=self.ws)
        self.decision = decisions.create_decision(
            self.meeting.id, "A decision that produced work", workspace_id=self.ws
        )
        self.owner = self.member("Owner One")
        self.other = self.member("Owner Two")

    def member(self, name: str) -> str:
        return board_members.create_member(
            name, "director", workspace_id=self.ws, actor_principal_id=self.actor,
        ).id

    def commitment(self, title: str = "Ship the pricing page", **kw):
        return commitments.create_commitment(
            self.decision.id, title, self.owner,
            workspace_id=self.ws, actor_principal_id=self.actor, **kw,
        )

    def events(self, aggregate_id: str | None = None) -> list:
        return audit.list_audit_events(
            aggregate_type="commitment", aggregate_id=aggregate_id, workspace_id=self.ws
        )

    def close(self) -> None:
        for table in ("audit_event", "commitment_update", "commitment", "resolution_vote",
                      "resolution", "board_member", "decision", "agenda_item", "meeting",
                      "membership"):
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
    """Actions in the order `list_audit_events` returns them: **newest first**.

    `ORDER BY created_at DESC, id DESC` — asserted as a sequence rather than sorted,
    as in `test_minutes_audit.py` and `test_resolutions_audit.py`.
    """
    return [e.action for e in events]


# ----------------------------------------------- the two that wrote nothing


def test_create_is_audited_with_the_actor(w):
    c = w.commitment(due_date=dt.date(2026, 12, 1), accountable_team="Growth")
    events = w.events(c.id)
    assert _newest_first(events) == ["created"]
    assert str(events[0].actor_principal_id) == w.actor
    p = events[0].payload
    assert p["status"] == "open"
    assert p["decision_id"] == w.decision.id
    assert p["owner_board_member_id"] == w.owner
    assert p["due_date"] == "2026-12-01"
    assert p["title"] == "Ship the pricing page"


def test_update_names_only_the_fields_the_caller_supplied(w):
    """A title edit says it was a title edit, and carries no owner or deadline history.

    `changed_fields` is derived from the supplied arguments, the same way the SET clause
    is, so an event cannot claim a field moved when the statement never wrote it.
    """
    c = w.commitment()
    commitments.update_commitment(
        c.id, expected_version=c.version, title="Ship the pricing page v2",
        workspace_id=w.ws, actor_principal_id=w.actor,
    )
    events = w.events(c.id)
    assert _newest_first(events) == ["updated", "created"]
    updated = events[0]
    assert str(updated.actor_principal_id) == w.actor
    assert updated.payload["changed_fields"] == ["title"]
    assert updated.payload["title"] == "Ship the pricing page v2"
    assert "from_due_date" not in updated.payload
    assert "from_owner_board_member_id" not in updated.payload


def test_a_moved_deadline_records_where_it_moved_from(w):
    """The renegotiation this aggregate exists to make visible.

    The resulting row says the deadline is now 1 March. Only the event can say it was
    1 December, and that is the half a board asks about.
    """
    c = w.commitment(due_date=dt.date(2026, 12, 1))
    moved = commitments.update_commitment(
        c.id, expected_version=c.version, due_date=dt.date(2027, 3, 1),
        workspace_id=w.ws, actor_principal_id=w.actor,
    )
    assert moved.due_date == dt.date(2027, 3, 1)
    updated = w.events(c.id)[0]
    assert updated.action == "updated"
    assert updated.payload["changed_fields"] == ["due_date"]
    assert updated.payload["from_due_date"] == "2026-12-01"
    assert updated.payload["due_date"] == "2027-03-01"


def test_a_deadline_set_for_the_first_time_records_that_there_was_none(w):
    """`from_due_date: null` is a fact — no deadline before — not a missing key."""
    c = w.commitment()
    commitments.update_commitment(
        c.id, expected_version=c.version, due_date=dt.date(2027, 1, 15),
        workspace_id=w.ws, actor_principal_id=w.actor,
    )
    payload = w.events(c.id)[0].payload
    assert "from_due_date" in payload and payload["from_due_date"] is None
    assert payload["due_date"] == "2027-01-15"


def test_a_reassigned_owner_records_who_owned_it_before(w):
    c = w.commitment()
    commitments.update_commitment(
        c.id, expected_version=c.version, owner_board_member_id=w.other,
        workspace_id=w.ws, actor_principal_id=w.actor,
    )
    updated = w.events(c.id)[0]
    assert updated.payload["changed_fields"] == ["owner_board_member_id"]
    assert updated.payload["from_owner_board_member_id"] == w.owner
    assert updated.payload["owner_board_member_id"] == w.other


# ----------------------------------------------- the one that was anonymous


def test_progress_now_names_the_caller_as_well_as_the_author(w):
    """`author_board_member_id` is the subject, supplied in the request body; the actor
    is who submitted it. Here they are deliberately different people.

    The payload shape is asserted exactly: it is unchanged from before this fix, so old
    and new events for the same act stay comparable.
    """
    c = w.commitment()
    commitments.record_update(
        c.id, "Kicked off with design", expected_version=c.version,
        new_status=commitments.IN_PROGRESS, author_board_member_id=w.other,
        workspace_id=w.ws, actor_principal_id=w.actor,
    )
    event = w.events(c.id)[0]
    assert event.action == "status_changed"
    assert str(event.actor_principal_id) == w.actor
    assert event.payload == {"new_status": "in_progress", "note": "Kicked off with design"}


def test_a_note_without_a_status_change_is_attributed_too(w):
    c = w.commitment()
    commitments.record_update(
        c.id, "Still on track", expected_version=c.version,
        workspace_id=w.ws, actor_principal_id=w.actor,
    )
    event = w.events(c.id)[0]
    assert event.action == "updated"
    assert str(event.actor_principal_id) == w.actor
    assert event.payload == {"new_status": None, "note": "Still on track"}


# ------------------------------------------------------- the second path in


def test_a_bridged_commitment_is_attributed_to_whoever_bridged_it(w):
    """`resolutions.bridge_resolution_to_commitment` is the second production caller of
    `create_commitment`, and before this change it passed no actor — so a commitment
    created from an adopted resolution got an anonymous `created` event.
    """
    r = resolutions.create_resolution(
        w.decision.id, "Adopt pricing B", "RESOLVED THAT pricing B is adopted.",
        workspace_id=w.ws, actor_principal_id=w.actor,
    )
    adopted = resolutions.transition_resolution(
        r.id, resolutions.ADOPTED, expected_version=r.version,
        workspace_id=w.ws, actor_principal_id=w.actor,
    )
    c = resolutions.bridge_resolution_to_commitment(
        adopted.id, w.owner, workspace_id=w.ws, actor_principal_id=w.actor,
    )
    events = w.events(c.id)
    assert _newest_first(events) == ["created"]
    assert str(events[0].actor_principal_id) == w.actor
    assert events[0].payload["title"] == "Adopt pricing B"


# ------------------------------------------------------------------ refusals


def test_a_refused_commitment_write_records_nothing(w):
    """Each refusal is a different branch, and none of them may leave an event.

    `rules.md` §2: the trail records only events that happened. A write placed before
    the mutation would record most of these as successes.
    """
    c = w.commitment()
    before = len(w.events())

    # create: a missing parent, and an owner who is no longer active.
    with pytest.raises(DecisionNotFound):
        commitments.create_commitment(
            str(uuid.uuid4()), "Orphaned", w.owner,
            workspace_id=w.ws, actor_principal_id=w.actor,
        )
    _admin("UPDATE board_member SET active = false WHERE id = %s", (w.other,))
    with pytest.raises(BoardMemberNotFound):
        commitments.create_commitment(
            w.decision.id, "Owned by a departed director", w.other,
            workspace_id=w.ws, actor_principal_id=w.actor,
        )

    # update: missing, stale, and reassigned to that inactive member.
    with pytest.raises(CommitmentNotFound):
        commitments.update_commitment(
            str(uuid.uuid4()), expected_version=1, title="x",
            workspace_id=w.ws, actor_principal_id=w.actor,
        )
    with pytest.raises(StaleCommitmentError):
        commitments.update_commitment(
            c.id, expected_version=c.version + 99, title="x",
            workspace_id=w.ws, actor_principal_id=w.actor,
        )
    with pytest.raises(BoardMemberNotFound):
        commitments.update_commitment(
            c.id, expected_version=c.version, owner_board_member_id=w.other,
            workspace_id=w.ws, actor_principal_id=w.actor,
        )

    assert len(w.events()) == before

    # Close it out — two recorded transitions — then try to edit history.
    started = commitments.record_update(
        c.id, "Started", expected_version=c.version, new_status=commitments.IN_PROGRESS,
        workspace_id=w.ws, actor_principal_id=w.actor,
    )
    done = commitments.record_update(
        c.id, "Shipped", expected_version=started.version, new_status=commitments.COMPLETED,
        workspace_id=w.ws, actor_principal_id=w.actor,
    )
    with pytest.raises(CommitmentLockedError):
        commitments.update_commitment(
            c.id, expected_version=done.version, due_date=dt.date(2030, 1, 1),
            workspace_id=w.ws, actor_principal_id=w.actor,
        )
    with pytest.raises(CommitmentLockedError):
        commitments.record_update(
            c.id, "Reopening", expected_version=done.version,
            new_status=commitments.IN_PROGRESS,
            workspace_id=w.ws, actor_principal_id=w.actor,
        )

    assert len(w.events()) == before + 2


def test_an_actor_outside_the_workspace_rolls_the_whole_mutation_back(w):
    """The audit write shares the mutation's transaction, so a bad actor takes the
    commitment down with it — the write is load-bearing, not decorative."""
    outsider = str(uuid.uuid4())
    _admin(
        "INSERT INTO principal (id, name, role, clearance) VALUES (%s, 'Outsider', 'observer', 0)",
        (outsider,),
    )
    try:
        with pytest.raises(audit.ActorNotInWorkspace):
            commitments.create_commitment(
                w.decision.id, "Should not survive", w.owner,
                workspace_id=w.ws, actor_principal_id=outsider,
            )
        assert commitments.list_commitments(workspace_id=w.ws) == []
        assert w.events() == []
    finally:
        _admin("DELETE FROM principal WHERE id = %s", (outsider,))


# ------------------------------------------------------------------- payload


def test_the_new_events_never_carry_the_detail_text(w):
    """`detail` is free text and stays out of the trail; who may read the trail is D7.

    Scoped to the two NEW events. `record_update`'s pre-existing payload carries `note`
    verbatim, and that is left unchanged on purpose — see the comment at the call site.
    """
    secret = "Contingent on the CFO's 185K retention package."
    c = w.commitment(detail=secret)
    commitments.update_commitment(
        c.id, expected_version=c.version, detail=secret + " Revised.",
        workspace_id=w.ws, actor_principal_id=w.actor,
    )
    for event in w.events(c.id):
        assert "185K" not in json.dumps(event.payload)
    assert w.events(c.id)[0].payload["changed_fields"] == ["detail"]
