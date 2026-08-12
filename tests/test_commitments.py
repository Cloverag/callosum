"""Live-store integration coverage for the Commitment aggregate (Meridian, checkpoint 7).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

The heaviest coverage is on FR-EXEC-03 — failed delivery must never falsely mark an
action delivered — because the proposal named it as the invariant to test hardest, and
because it is enforced by a CHECK constraint that has to be proved against direct SQL,
not just against the domain module.
"""

import os
import uuid
from datetime import date, timedelta

import pytest

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip("set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests", allow_module_level=True)

import psycopg

from callosum.config import settings
from meridian import board_members, commitments, decisions, meetings, resolutions
from meridian.board_members import DIRECTOR
from meridian.commitments import (
    BLOCKED,
    CANCELLED,
    COMPLETED,
    DELIVERED,
    FAILED,
    IN_PROGRESS,
    NOT_DISPATCHED,
    OPEN,
    PENDING,
    BoardMemberNotFound,
    CommitmentLockedError,
    CommitmentNotFound,
    CommitmentValidationError,
    DecisionNotFound,
    ResolutionNotFound,
    StaleCommitmentError,
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
        (ws, f"cmt-{ws[:8]}", ws),
    )
    return ws


def _cleanup(*workspace_ids: str) -> None:
    for ws in workspace_ids:
        _admin("DELETE FROM commitment_update WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM commitment WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM resolution_vote WHERE workspace_id = %s", (ws,))
        _admin("UPDATE resolution SET superseded_by_id = NULL WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM resolution WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM decision_stance WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM decision WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM board_member WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM meeting WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM membership WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM workspace WHERE id = %s", (ws,))


def _fixture(ws: str):
    """A meeting -> decision -> owner triple, the minimum a commitment needs."""
    m = meetings.create_meeting("Board Meeting", workspace_id=ws)
    dec = decisions.create_decision(m.id, "Ship the thing", workspace_id=ws)
    owner = board_members.create_member("Priya Nair", DIRECTOR, workspace_id=ws)
    return m, dec, owner


def _commitment(ws: str, **kw):
    _, dec, owner = _fixture(ws)
    return dec, owner, commitments.create_commitment(
        dec.id, kw.pop("title", "Deliver the migration plan"), owner.id, workspace_id=ws, **kw
    )


# ---------------------------------------------------------------------------
# Creation and the source-decision rule
# ---------------------------------------------------------------------------

def test_create_commitment_starts_open_and_undispatched():
    ws = _new_workspace()
    try:
        _, _, c = _commitment(ws)
        assert c.status == OPEN
        assert c.version == 1
        assert c.completed_at is None
        assert c.updates == []
        # No adapter exists in P2, so undispatched is the only honest start.
        assert c.delivery_status == NOT_DISPATCHED
        assert c.delivery_attempts == 0
        assert c.external_task_id is None
        assert c.is_open is True
    finally:
        _cleanup(ws)


def test_a_commitment_cannot_exist_without_a_source_decision():
    """The proposal's hard rule: untraceable work is what this product prevents."""
    ws = _new_workspace()
    try:
        _, _, owner = _fixture(ws)
        with pytest.raises(DecisionNotFound):
            commitments.create_commitment(
                str(uuid.uuid4()), "Orphan work", owner.id, workspace_id=ws
            )
    finally:
        _cleanup(ws)


def test_decision_id_is_not_nullable_at_the_schema_level():
    # Asserted through the superuser connection: the domain check above can be
    # bypassed, a NOT NULL cannot.
    ws = _new_workspace()
    try:
        _, _, owner = _fixture(ws)
        with psycopg.connect(settings().postgres_dsn) as conn:
            with pytest.raises(psycopg.errors.NotNullViolation):
                conn.execute(
                    """
                    INSERT INTO commitment (title, owner_board_member_id, workspace_id)
                    VALUES ('Orphan', %s, %s)
                    """,
                    (owner.id, ws),
                )
            conn.rollback()
    finally:
        _cleanup(ws)


def test_create_rejects_an_empty_title():
    ws = _new_workspace()
    try:
        _, dec, owner = _fixture(ws)
        with pytest.raises(CommitmentValidationError):
            commitments.create_commitment(dec.id, "   ", owner.id, workspace_id=ws)
    finally:
        _cleanup(ws)


def test_owner_must_be_an_active_board_member():
    ws = _new_workspace()
    try:
        _, dec, owner = _fixture(ws)
        board_members.deactivate_member(owner.id, expected_version=1, workspace_id=ws)

        with pytest.raises(BoardMemberNotFound):
            commitments.create_commitment(dec.id, "Work", owner.id, workspace_id=ws)
        # Absent and inactive are refused identically — distinguishing them would
        # confirm a directory entry to a caller who cannot read the directory.
        with pytest.raises(BoardMemberNotFound):
            commitments.create_commitment(dec.id, "Work", str(uuid.uuid4()), workspace_id=ws)
    finally:
        _cleanup(ws)


def test_a_cited_resolution_must_belong_to_the_same_decision():
    """A wrong citation is worse than none: it looks like provenance."""
    ws = _new_workspace()
    try:
        m, dec_a, owner = _fixture(ws)
        dec_b = decisions.create_decision(m.id, "An unrelated decision", workspace_id=ws)
        res_b = resolutions.create_resolution(dec_b.id, "R-B", "body", workspace_id=ws)

        with pytest.raises(CommitmentValidationError):
            commitments.create_commitment(
                dec_a.id, "Work", owner.id, resolution_id=res_b.id, workspace_id=ws
            )

        # The matching resolution is accepted.
        res_a = resolutions.create_resolution(dec_a.id, "R-A", "body", workspace_id=ws)
        c = commitments.create_commitment(
            dec_a.id, "Work", owner.id, resolution_id=res_a.id, workspace_id=ws
        )
        assert c.resolution_id == res_a.id
    finally:
        _cleanup(ws)


def test_a_missing_resolution_is_reported_as_such():
    ws = _new_workspace()
    try:
        _, dec, owner = _fixture(ws)
        with pytest.raises(ResolutionNotFound):
            commitments.create_commitment(
                dec.id, "Work", owner.id, resolution_id=str(uuid.uuid4()), workspace_id=ws
            )
    finally:
        _cleanup(ws)


def test_a_commitment_outlives_its_meeting():
    """Deliberately NOT locked to meeting status, unlike resolutions.

    Reporting progress at the next meeting is the point of the object, so a
    completed meeting must not freeze the work it produced.
    """
    ws = _new_workspace()
    try:
        m, dec, owner = _fixture(ws)
        c = commitments.create_commitment(dec.id, "Ongoing work", owner.id, workspace_id=ws)
        meetings.transition_status(m.id, meetings.CANCELLED, expected_version=1, workspace_id=ws)

        moved = commitments.record_update(
            c.id, "Still going after the meeting closed",
            new_status=IN_PROGRESS, expected_version=c.version, workspace_id=ws,
        )
        assert moved.status == IN_PROGRESS
    finally:
        _cleanup(ws)


# ---------------------------------------------------------------------------
# FR-EXEC-03 — the invariant to test hardest
# ---------------------------------------------------------------------------

def test_delivered_requires_an_external_reference_via_the_module():
    ws = _new_workspace()
    try:
        _, _, c = _commitment(ws)
        with pytest.raises(CommitmentValidationError):
            commitments.record_delivery_attempt(
                c.id, DELIVERED, expected_version=c.version, workspace_id=ws
            )
    finally:
        _cleanup(ws)


def test_delivered_without_an_external_reference_is_refused_by_the_DATABASE():
    """FR-EXEC-03 as a CHECK constraint, proved against direct SQL.

    Asserted through the SUPERUSER connection on purpose. The domain module's
    validation only protects callers who go through it; the constraint is what makes
    a false 'delivered' impossible for a bad migration, a direct write, or the P8
    adapter that does not exist yet.
    """
    ws = _new_workspace()
    try:
        _, _, c = _commitment(ws)
        with psycopg.connect(settings().postgres_dsn) as conn:
            # No external reference at all.
            with pytest.raises(psycopg.errors.CheckViolation):
                conn.execute(
                    "UPDATE commitment SET delivery_status = 'delivered' WHERE id = %s",
                    (c.id,),
                )
            conn.rollback()

            # A task id with no system: unresolvable, so still not a delivery.
            with pytest.raises(psycopg.errors.CheckViolation):
                conn.execute(
                    """
                    UPDATE commitment
                       SET delivery_status = 'delivered', external_task_id = 'JIRA-1'
                     WHERE id = %s
                    """,
                    (c.id,),
                )
            conn.rollback()
    finally:
        _cleanup(ws)


def test_a_failed_delivery_leaves_the_commitment_undelivered():
    ws = _new_workspace()
    try:
        _, _, c = _commitment(ws)
        failed = commitments.record_delivery_attempt(
            c.id, FAILED, expected_version=c.version,
            external_system="jira", workspace_id=ws,
        )
        assert failed.delivery_status == FAILED
        assert failed.external_task_id is None
        assert failed.delivery_attempts == 1
        # The work itself is untouched by a delivery failure.
        assert failed.status == OPEN
    finally:
        _cleanup(ws)


def test_delivery_succeeds_once_there_is_something_to_reconcile_against():
    ws = _new_workspace()
    try:
        _, _, c = _commitment(ws)
        delivered = commitments.record_delivery_attempt(
            c.id, DELIVERED, expected_version=c.version,
            external_system="jira", external_task_id="JIRA-42", workspace_id=ws,
        )
        assert delivered.delivery_status == DELIVERED
        assert (delivered.external_system, delivered.external_task_id) == ("jira", "JIRA-42")
    finally:
        _cleanup(ws)


def test_attempts_count_every_try_including_the_successful_one():
    ws = _new_workspace()
    try:
        _, _, c = _commitment(ws)
        c = commitments.record_delivery_attempt(
            c.id, FAILED, expected_version=c.version, external_system="jira", workspace_id=ws
        )
        c = commitments.record_delivery_attempt(
            c.id, PENDING, expected_version=c.version, workspace_id=ws
        )
        c = commitments.record_delivery_attempt(
            c.id, DELIVERED, expected_version=c.version,
            external_task_id="JIRA-42", workspace_id=ws,
        )
        # "How many times we tried", not "how many times we failed".
        assert c.delivery_attempts == 3
        # external_system persisted from the first attempt rather than being cleared
        # by later calls that did not supply it.
        assert c.external_system == "jira"
    finally:
        _cleanup(ws)


def test_delivery_attempts_cannot_go_negative():
    ws = _new_workspace()
    try:
        _, _, c = _commitment(ws)
        with psycopg.connect(settings().postgres_dsn) as conn:
            with pytest.raises(psycopg.errors.CheckViolation):
                conn.execute(
                    "UPDATE commitment SET delivery_attempts = -1 WHERE id = %s", (c.id,)
                )
            conn.rollback()
    finally:
        _cleanup(ws)


def test_unknown_delivery_status_is_rejected():
    ws = _new_workspace()
    try:
        _, _, c = _commitment(ws)
        with pytest.raises(CommitmentValidationError):
            commitments.record_delivery_attempt(
                c.id, "sent-ish", expected_version=c.version, workspace_id=ws
            )
    finally:
        _cleanup(ws)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def test_the_happy_path_open_to_completed():
    ws = _new_workspace()
    try:
        _, _, c = _commitment(ws)
        c = commitments.record_update(
            c.id, "Started", new_status=IN_PROGRESS, expected_version=c.version, workspace_id=ws
        )
        assert c.status == IN_PROGRESS

        c = commitments.record_update(
            c.id, "Done", new_status=COMPLETED, expected_version=c.version, workspace_id=ws
        )
        assert c.status == COMPLETED
        assert c.completed_at is not None
        assert c.is_open is False
    finally:
        _cleanup(ws)


def test_blocked_is_not_terminal():
    """A blocked task is expected to resume.

    Making `blocked` an exit would repeat the `deferred` (CP4) and `archived` (CP6)
    mistake of minting a status nothing can leave.
    """
    ws = _new_workspace()
    try:
        _, _, c = _commitment(ws)
        c = commitments.record_update(
            c.id, "Waiting on legal", new_status=BLOCKED,
            expected_version=c.version, workspace_id=ws,
        )
        assert c.status == BLOCKED

        c = commitments.record_update(
            c.id, "Legal cleared it", new_status=IN_PROGRESS,
            expected_version=c.version, workspace_id=ws,
        )
        assert c.status == IN_PROGRESS
        assert c.is_open is True
    finally:
        _cleanup(ws)


def test_work_can_be_blocked_before_it_starts():
    ws = _new_workspace()
    try:
        _, _, c = _commitment(ws)
        c = commitments.record_update(
            c.id, "Blocked from the outset", new_status=BLOCKED,
            expected_version=c.version, workspace_id=ws,
        )
        assert c.status == BLOCKED
    finally:
        _cleanup(ws)


def _drive_to(ws: str, c, terminal: str):
    """Walk a commitment to a terminal state through legal transitions.

    `cancelled` is reachable from `open`; `completed` is not, because open ->
    completed would skip the work. That asymmetry is the point of the state machine,
    so the helper respects it rather than routing around it.
    """
    if terminal == COMPLETED:
        c = commitments.record_update(
            c.id, "Started", new_status=IN_PROGRESS, expected_version=c.version, workspace_id=ws
        )
    return commitments.record_update(
        c.id, "Closing", new_status=terminal, expected_version=c.version, workspace_id=ws
    )


@pytest.mark.parametrize("terminal", [COMPLETED, CANCELLED])
def test_completed_and_cancelled_are_terminal(terminal):
    ws = _new_workspace()
    try:
        _, _, c = _commitment(ws)
        c = _drive_to(ws, c, terminal)
        for target in (OPEN, IN_PROGRESS, BLOCKED, COMPLETED, CANCELLED):
            with pytest.raises(CommitmentLockedError):
                commitments.record_update(
                    c.id, "Reopening", new_status=target,
                    expected_version=c.version, workspace_id=ws,
                )
    finally:
        _cleanup(ws)


def test_a_terminal_commitment_cannot_be_edited():
    ws = _new_workspace()
    try:
        _, _, c = _commitment(ws)
        c = _drive_to(ws, c, COMPLETED)
        # Rewriting the deadline or owner of finished work would falsify what was agreed.
        with pytest.raises(CommitmentLockedError):
            commitments.update_commitment(
                c.id, expected_version=c.version, due_date=date(2027, 1, 1), workspace_id=ws
            )
    finally:
        _cleanup(ws)


def test_an_illegal_transition_is_refused():
    ws = _new_workspace()
    try:
        _, _, c = _commitment(ws)
        # open -> completed skips the work.
        with pytest.raises(CommitmentLockedError):
            commitments.record_update(
                c.id, "Skipping ahead", new_status=COMPLETED,
                expected_version=c.version, workspace_id=ws,
            )
    finally:
        _cleanup(ws)


def test_unknown_status_is_rejected():
    ws = _new_workspace()
    try:
        _, _, c = _commitment(ws)
        with pytest.raises(CommitmentValidationError):
            commitments.record_update(
                c.id, "note", new_status="nearly-done",
                expected_version=c.version, workspace_id=ws,
            )
    finally:
        _cleanup(ws)


# ---------------------------------------------------------------------------
# The update trail
# ---------------------------------------------------------------------------

def test_a_status_change_always_carries_its_reason():
    """The difference between a status field and a record.

    `record_update` is the only path that moves status, and it requires a note — so
    the trail cannot contain a state change with no account of why it happened.
    """
    ws = _new_workspace()
    try:
        _, _, c = _commitment(ws)
        with pytest.raises(CommitmentValidationError):
            commitments.record_update(
                c.id, "   ", new_status=IN_PROGRESS,
                expected_version=c.version, workspace_id=ws,
            )
    finally:
        _cleanup(ws)


def test_progress_can_be_recorded_without_changing_status():
    ws = _new_workspace()
    try:
        _, _, c = _commitment(ws)
        c = commitments.record_update(
            c.id, "Draft circulated for comment", expected_version=c.version, workspace_id=ws
        )
        assert c.status == OPEN
        assert len(c.updates) == 1
        assert c.updates[0].new_status is None
    finally:
        _cleanup(ws)


def test_the_trail_is_ordered_and_records_the_transitions():
    ws = _new_workspace()
    try:
        _, _, c = _commitment(ws)
        c = commitments.record_update(
            c.id, "Started", new_status=IN_PROGRESS, expected_version=c.version, workspace_id=ws
        )
        c = commitments.record_update(c.id, "Halfway", expected_version=c.version, workspace_id=ws)
        c = commitments.record_update(
            c.id, "Done", new_status=COMPLETED, expected_version=c.version, workspace_id=ws
        )

        assert [u.note for u in c.updates] == ["Started", "Halfway", "Done"]
        assert [u.new_status for u in c.updates] == [IN_PROGRESS, None, COMPLETED]
    finally:
        _cleanup(ws)


def test_the_trail_is_append_only_at_the_module_level():
    # There is no edit or delete operation, deliberately: an editable trail is not
    # evidence. This pins the absence so it cannot be added without a decision.
    for name in ("edit_update", "delete_update", "remove_update", "update_update"):
        assert not hasattr(commitments, name)


def test_an_update_author_must_be_an_active_member():
    ws = _new_workspace()
    try:
        _, _, c = _commitment(ws)
        ghost = board_members.create_member("Departed", DIRECTOR, workspace_id=ws)
        board_members.deactivate_member(ghost.id, expected_version=1, workspace_id=ws)

        with pytest.raises(BoardMemberNotFound):
            commitments.record_update(
                c.id, "note", author_board_member_id=ghost.id,
                expected_version=c.version, workspace_id=ws,
            )
    finally:
        _cleanup(ws)


def test_deleting_a_member_who_owns_work_is_refused():
    ws = _new_workspace()
    try:
        _, owner, _ = _commitment(ws)
        with psycopg.connect(settings().postgres_dsn) as conn:
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                conn.execute("DELETE FROM board_member WHERE id = %s", (owner.id,))
            conn.rollback()
    finally:
        _cleanup(ws)


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

def test_is_overdue_takes_today_rather_than_reading_the_clock():
    ws = _new_workspace()
    try:
        _, dec, owner = _fixture(ws)
        due = date(2026, 7, 1)
        c = commitments.create_commitment(
            dec.id, "Late work", owner.id, due_date=due, workspace_id=ws
        )
        assert c.is_overdue(today=due + timedelta(days=1)) is True
        assert c.is_overdue(today=due) is False
        assert c.is_overdue(today=due - timedelta(days=1)) is False
    finally:
        _cleanup(ws)


def test_closed_work_is_never_overdue():
    ws = _new_workspace()
    try:
        _, dec, owner = _fixture(ws)
        c = commitments.create_commitment(
            dec.id, "Finished late", owner.id, due_date=date(2026, 7, 1), workspace_id=ws
        )
        c = commitments.record_update(
            c.id, "Started", new_status=IN_PROGRESS, expected_version=c.version, workspace_id=ws
        )
        c = commitments.record_update(
            c.id, "Done, late", new_status=COMPLETED, expected_version=c.version, workspace_id=ws
        )
        # It was delivered late, but it is not outstanding — an overdue list that
        # includes finished work is not an overdue list.
        assert c.is_overdue(today=date(2026, 12, 31)) is False
    finally:
        _cleanup(ws)


def test_undated_work_is_never_overdue():
    ws = _new_workspace()
    try:
        _, _, c = _commitment(ws)
        assert c.due_date is None
        assert c.is_overdue(today=date(2099, 1, 1)) is False
    finally:
        _cleanup(ws)


def test_list_orders_by_due_date_with_undated_work_last():
    ws = _new_workspace()
    try:
        _, dec, owner = _fixture(ws)
        commitments.create_commitment(
            dec.id, "No deadline", owner.id, workspace_id=ws
        )
        commitments.create_commitment(
            dec.id, "Later", owner.id, due_date=date(2026, 9, 1), workspace_id=ws
        )
        commitments.create_commitment(
            dec.id, "Sooner", owner.id, due_date=date(2026, 8, 1), workspace_id=ws
        )

        # Undated work is not the most urgent thing on the list.
        assert [c.title for c in commitments.list_commitments(workspace_id=ws)] == [
            "Sooner", "Later", "No deadline",
        ]
    finally:
        _cleanup(ws)


def test_list_filters_by_decision_owner_status_and_openness():
    ws = _new_workspace()
    try:
        m, dec_a, owner_a = _fixture(ws)
        dec_b = decisions.create_decision(m.id, "Second decision", workspace_id=ws)
        owner_b = board_members.create_member("Marcus Webb", DIRECTOR, workspace_id=ws)

        a = commitments.create_commitment(dec_a.id, "A", owner_a.id, workspace_id=ws)
        commitments.create_commitment(dec_b.id, "B", owner_b.id, workspace_id=ws)
        commitments.record_update(
            a.id, "Cancelled", new_status=CANCELLED, expected_version=a.version, workspace_id=ws
        )

        assert [c.title for c in commitments.list_commitments(decision_id=dec_b.id, workspace_id=ws)] == ["B"]
        assert [c.title for c in commitments.list_commitments(owner_board_member_id=owner_b.id, workspace_id=ws)] == ["B"]
        assert [c.title for c in commitments.list_commitments(status=CANCELLED, workspace_id=ws)] == ["A"]
        # open_only answers the question a board actually asks, which no single
        # status answers.
        assert [c.title for c in commitments.list_commitments(open_only=True, workspace_id=ws)] == ["B"]
    finally:
        _cleanup(ws)


def test_list_rejects_an_unknown_status_filter():
    ws = _new_workspace()
    try:
        with pytest.raises(CommitmentValidationError):
            commitments.list_commitments(status="nearly-done", workspace_id=ws)
    finally:
        _cleanup(ws)


# ---------------------------------------------------------------------------
# Optimistic concurrency
# ---------------------------------------------------------------------------

def test_every_mutation_is_version_guarded():
    ws = _new_workspace()
    try:
        _, _, c = _commitment(ws)
        stale = c.version - 1

        with pytest.raises(StaleCommitmentError):
            commitments.update_commitment(c.id, expected_version=stale, title="x", workspace_id=ws)
        with pytest.raises(StaleCommitmentError):
            commitments.record_update(c.id, "note", expected_version=stale, workspace_id=ws)
        with pytest.raises(StaleCommitmentError):
            commitments.record_delivery_attempt(
                c.id, PENDING, expected_version=stale, workspace_id=ws
            )
    finally:
        _cleanup(ws)


def test_a_rejected_update_writes_no_trail_entry():
    # The insert and the version-guarded update share a transaction, so a stale
    # write must not leave an orphan note behind.
    ws = _new_workspace()
    try:
        _, _, c = _commitment(ws)
        with pytest.raises(StaleCommitmentError):
            commitments.record_update(
                c.id, "should not persist", expected_version=c.version - 1, workspace_id=ws
            )
        assert commitments.get_commitment(c.id, workspace_id=ws).updates == []
    finally:
        _cleanup(ws)


def test_update_requires_at_least_one_field():
    ws = _new_workspace()
    try:
        _, _, c = _commitment(ws)
        with pytest.raises(CommitmentValidationError):
            commitments.update_commitment(c.id, expected_version=c.version, workspace_id=ws)
    finally:
        _cleanup(ws)


def test_reassigning_an_owner_requires_an_active_member():
    ws = _new_workspace()
    try:
        _, _, c = _commitment(ws)
        successor = board_members.create_member("Elena Fischer", DIRECTOR, workspace_id=ws)

        moved = commitments.update_commitment(
            c.id, expected_version=c.version,
            owner_board_member_id=successor.id, workspace_id=ws,
        )
        assert moved.owner_board_member_id == successor.id

        board_members.deactivate_member(successor.id, expected_version=1, workspace_id=ws)
        with pytest.raises(BoardMemberNotFound):
            commitments.update_commitment(
                moved.id, expected_version=moved.version,
                owner_board_member_id=successor.id, workspace_id=ws,
            )
    finally:
        _cleanup(ws)


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------

def test_cross_workspace_isolation():
    ws_a, ws_b = _new_workspace(), _new_workspace()
    try:
        _, _, c_a = _commitment(ws_a, title="Secret work in A")

        with pytest.raises(CommitmentNotFound):
            commitments.get_commitment(c_a.id, workspace_id=ws_b)
        assert commitments.list_commitments(workspace_id=ws_b) == []
        with pytest.raises(CommitmentNotFound):
            commitments.record_update(c_a.id, "note", expected_version=1, workspace_id=ws_b)
    finally:
        _cleanup(ws_a, ws_b)


def test_a_commitment_cannot_reference_another_workspaces_decision():
    """Composite FK, asserted through the SUPERUSER connection.

    Superuser bypasses RLS, so a rejection there proves the constraint is doing the
    work rather than the policy.
    """
    ws_a, ws_b = _new_workspace(), _new_workspace()
    try:
        _, dec_b, _ = _fixture(ws_b)
        _, owner_a, _ = _commitment(ws_a)

        with psycopg.connect(settings().postgres_dsn) as conn:
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                conn.execute(
                    """
                    INSERT INTO commitment
                        (decision_id, title, owner_board_member_id, workspace_id)
                    VALUES (%s, 'Cross-tenant', %s, %s)
                    """,
                    (dec_b.id, owner_a.id, ws_a),
                )
            conn.rollback()
    finally:
        _cleanup(ws_a, ws_b)


def test_a_commitment_cannot_be_owned_by_another_workspaces_member():
    ws_a, ws_b = _new_workspace(), _new_workspace()
    try:
        owner_b = board_members.create_member("Director B", DIRECTOR, workspace_id=ws_b)
        _, dec_a, _ = _fixture(ws_a)

        with psycopg.connect(settings().postgres_dsn) as conn:
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                conn.execute(
                    """
                    INSERT INTO commitment
                        (decision_id, title, owner_board_member_id, workspace_id)
                    VALUES (%s, 'Cross-tenant owner', %s, %s)
                    """,
                    (dec_a.id, owner_b.id, ws_a),
                )
            conn.rollback()
    finally:
        _cleanup(ws_a, ws_b)
