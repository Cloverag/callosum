"""Live-store integration coverage for the Resolution aggregate (Meridian, checkpoint 6).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``. These exercise
the aggregate against a real Postgres: the status machine, the frozen voting record,
per-motion recusal, supersession, optimistic concurrency, composite-FK tenant isolation,
and Row-Level Security.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip("set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests", allow_module_level=True)

import psycopg

from callosum.config import settings
from meridian import board_members, decisions, meetings, resolutions
from meridian.board_members import DIRECTOR, NON_VOTING, OBSERVER, RECUSED, VOTING
from meridian.resolutions import (
    ADOPTED,
    DRAFT,
    REJECTED,
    SUPERSEDED,
    VOTE_ABSTAIN,
    VOTE_AGAINST,
    VOTE_FOR,
    VOTE_RECUSED,
    BoardMemberNotFound,
    DecisionNotFound,
    ResolutionLockedError,
    ResolutionNotFound,
    ResolutionValidationError,
    StaleResolutionError,
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
        (ws, f"res-{ws[:8]}", ws),
    )
    return ws


def _cleanup(*workspace_ids: str) -> None:
    for ws in workspace_ids:
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM resolution_vote WHERE workspace_id = %s", (ws,))
        _admin("UPDATE resolution SET superseded_by_id = NULL WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM resolution WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM decision_stance WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM decision WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM board_member WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM meeting WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM membership WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM workspace WHERE id = %s", (ws,))


def _decision(ws: str, title: str = "A decision"):
    m = meetings.create_meeting("Board Meeting", workspace_id=ws)
    return m, decisions.create_decision(m.id, title, workspace_id=ws)


def _resolution(ws: str, title: str = "Resolution 1"):
    _, dec = _decision(ws)
    return dec, resolutions.create_resolution(dec.id, title, "RESOLVED THAT …", workspace_id=ws)


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------

def test_create_resolution_starts_as_an_unvoted_draft():
    ws = _new_workspace()
    try:
        _, res = _resolution(ws)
        assert res.status == DRAFT
        assert res.version_no == 1
        assert res.version == 1
        assert res.adopted_at is None
        assert res.superseded_by_id is None
        assert res.votes == []
        # The legal-scope guard: one value, and it is the inert one.
        assert res.signing_state == "not_applicable"
    finally:
        _cleanup(ws)


def test_create_rejects_empty_title_or_body():
    ws = _new_workspace()
    try:
        _, dec = _decision(ws)
        with pytest.raises(ResolutionValidationError):
            resolutions.create_resolution(dec.id, "   ", "body", workspace_id=ws)
        with pytest.raises(ResolutionValidationError):
            resolutions.create_resolution(dec.id, "title", "   ", workspace_id=ws)
    finally:
        _cleanup(ws)


def test_create_requires_a_visible_decision():
    ws = _new_workspace()
    try:
        with pytest.raises(DecisionNotFound):
            resolutions.create_resolution(str(uuid.uuid4()), "t", "b", workspace_id=ws)
    finally:
        _cleanup(ws)


def test_resolution_is_locked_to_a_live_meeting():
    ws = _new_workspace()
    try:
        m, dec = _decision(ws)
        meetings.transition_status(m.id, meetings.CANCELLED, expected_version=1, workspace_id=ws)
        with pytest.raises(ResolutionLockedError):
            resolutions.create_resolution(dec.id, "Late", "body", workspace_id=ws)
    finally:
        _cleanup(ws)


def test_a_resolution_can_be_drafted_during_a_live_meeting():
    # The lock set matches decisions.py, not agenda.py: resolutions are moved and
    # voted on while the meeting is happening, so `in_progress` must stay open.
    ws = _new_workspace()
    try:
        # A meeting needs a concrete window before it can be scheduled, which is
        # the only route to `in_progress`.
        start = datetime(2026, 7, 28, 9, 0, tzinfo=timezone.utc)
        m = meetings.create_meeting(
            "Live",
            workspace_id=ws,
            scheduled_start=start,
            scheduled_end=start + timedelta(hours=2),
        )
        m = meetings.transition_status(m.id, meetings.SCHEDULED, expected_version=1, workspace_id=ws)
        m = meetings.transition_status(m.id, meetings.IN_PROGRESS, expected_version=m.version, workspace_id=ws)
        dec = decisions.create_decision(m.id, "Live decision", workspace_id=ws)
        res = resolutions.create_resolution(dec.id, "Live resolution", "body", workspace_id=ws)
        assert res.status == DRAFT
    finally:
        _cleanup(ws)


# ---------------------------------------------------------------------------
# Voting
# ---------------------------------------------------------------------------

def test_record_and_change_a_vote_preserves_created_at():
    ws = _new_workspace()
    try:
        _, res = _resolution(ws)
        member = board_members.create_member("Priya Nair", DIRECTOR, workspace_id=ws)

        first = resolutions.record_vote(res.id, member.id, VOTE_FOR, workspace_id=ws)
        changed = resolutions.record_vote(res.id, member.id, VOTE_AGAINST, workspace_id=ws)

        assert changed.vote == VOTE_AGAINST
        assert changed.id == first.id, "changing a vote must update the row, not add one"
        # The CP4 review finding, applied from the start: when a director FIRST voted
        # is audit history and must survive them changing their mind.
        assert changed.created_at == first.created_at
        assert changed.updated_at > first.updated_at

        assert len(resolutions.get_resolution(res.id, workspace_id=ws).votes) == 1
    finally:
        _cleanup(ws)


def test_one_vote_per_member_per_motion():
    ws = _new_workspace()
    try:
        _, res = _resolution(ws)
        a = board_members.create_member("Director A", DIRECTOR, workspace_id=ws)
        b = board_members.create_member("Director B", DIRECTOR, workspace_id=ws)

        resolutions.record_vote(res.id, a.id, VOTE_FOR, workspace_id=ws)
        resolutions.record_vote(res.id, b.id, VOTE_AGAINST, workspace_id=ws)

        assert len(resolutions.get_resolution(res.id, workspace_id=ws).votes) == 2
    finally:
        _cleanup(ws)


def test_unknown_vote_is_rejected():
    ws = _new_workspace()
    try:
        _, res = _resolution(ws)
        member = board_members.create_member("Director", DIRECTOR, workspace_id=ws)
        with pytest.raises(ResolutionValidationError):
            resolutions.record_vote(res.id, member.id, "maybe", workspace_id=ws)
    finally:
        _cleanup(ws)


def test_a_non_voting_member_cannot_vote_but_can_be_recused():
    ws = _new_workspace()
    try:
        _, res = _resolution(ws)
        observer = board_members.create_member(
            "Observer", OBSERVER, voting=NON_VOTING, workspace_id=ws
        )

        for vote in (VOTE_FOR, VOTE_AGAINST, VOTE_ABSTAIN):
            with pytest.raises(ResolutionValidationError):
                resolutions.record_vote(res.id, observer.id, vote, workspace_id=ws)

        # Recusal stays permitted so a standing conflict can still be minuted
        # against this motion.
        recusal = resolutions.record_vote(res.id, observer.id, VOTE_RECUSED, workspace_id=ws)
        assert recusal.vote == VOTE_RECUSED
    finally:
        _cleanup(ws)


def test_per_motion_recusal_is_independent_of_standing_status():
    # board_member.voting is the STANDING status; recusal from one motion is a
    # property of the vote. CP5a deferred this here deliberately.
    ws = _new_workspace()
    try:
        _, res = _resolution(ws)
        member = board_members.create_member(
            "Conflicted Director", DIRECTOR, voting=VOTING, workspace_id=ws
        )

        resolutions.record_vote(res.id, member.id, VOTE_RECUSED, workspace_id=ws)

        assert board_members.get_member(member.id, workspace_id=ws).voting == VOTING
        assert resolutions.get_resolution(res.id, workspace_id=ws).votes[0].vote == VOTE_RECUSED
    finally:
        _cleanup(ws)


def test_votes_from_an_inactive_or_unknown_member_are_refused_identically():
    ws = _new_workspace()
    try:
        _, res = _resolution(ws)
        member = board_members.create_member("Departed", DIRECTOR, workspace_id=ws)
        board_members.deactivate_member(member.id, expected_version=1, workspace_id=ws)

        with pytest.raises(BoardMemberNotFound):
            resolutions.record_vote(res.id, member.id, VOTE_FOR, workspace_id=ws)
        with pytest.raises(BoardMemberNotFound):
            resolutions.record_vote(res.id, str(uuid.uuid4()), VOTE_FOR, workspace_id=ws)
    finally:
        _cleanup(ws)


def test_the_voting_record_freezes_once_the_outcome_is_recorded():
    """The load-bearing rule of this checkpoint.

    A board's voting record is the evidence for the outcome. If it stays editable
    after adoption, the record can be made to contradict the result it produced.
    """
    ws = _new_workspace()
    try:
        _, res = _resolution(ws)
        a = board_members.create_member("Director A", DIRECTOR, workspace_id=ws)
        b = board_members.create_member("Director B", DIRECTOR, workspace_id=ws)
        resolutions.record_vote(res.id, a.id, VOTE_FOR, workspace_id=ws)

        res = resolutions.get_resolution(res.id, workspace_id=ws)
        res = resolutions.transition_resolution(
            res.id, ADOPTED, expected_version=res.version, workspace_id=ws
        )

        # No new votes...
        with pytest.raises(ResolutionLockedError):
            resolutions.record_vote(res.id, b.id, VOTE_AGAINST, workspace_id=ws)
        # ...and no changing an existing one.
        with pytest.raises(ResolutionLockedError):
            resolutions.record_vote(res.id, a.id, VOTE_AGAINST, workspace_id=ws)
    finally:
        _cleanup(ws)


# ---------------------------------------------------------------------------
# Tally
# ---------------------------------------------------------------------------

def test_tally_counts_each_vote_and_excludes_abstain_and_recusal():
    ws = _new_workspace()
    try:
        _, res = _resolution(ws)
        names = ["A", "B", "C", "D", "E"]
        members = [board_members.create_member(n, DIRECTOR, workspace_id=ws) for n in names]
        cast = [VOTE_FOR, VOTE_FOR, VOTE_AGAINST, VOTE_ABSTAIN, VOTE_RECUSED]
        for member, vote in zip(members, cast):
            resolutions.record_vote(res.id, member.id, vote, workspace_id=ws)

        t = resolutions.tally(resolutions.get_resolution(res.id, workspace_id=ws))

        assert (t.for_, t.against, t.abstain, t.recused) == (2, 1, 1, 1)
        # An abstention is a deliberate non-vote and a recusal is a declared
        # conflict. Counting either as opposition would misreport the board.
        assert t.counted == 3
        assert t.carried is True
    finally:
        _cleanup(ws)


def test_a_tie_does_not_carry():
    ws = _new_workspace()
    try:
        _, res = _resolution(ws)
        a = board_members.create_member("A", DIRECTOR, workspace_id=ws)
        b = board_members.create_member("B", DIRECTOR, workspace_id=ws)
        resolutions.record_vote(res.id, a.id, VOTE_FOR, workspace_id=ws)
        resolutions.record_vote(res.id, b.id, VOTE_AGAINST, workspace_id=ws)

        assert resolutions.tally(resolutions.get_resolution(res.id, workspace_id=ws)).carried is False
    finally:
        _cleanup(ws)


def test_the_tally_does_not_decide_the_outcome():
    """`carried` is advisory; `status` is authoritative and set by a human.

    Quorum and supermajority rules vary per board and the product has nowhere to
    record them, so deriving the outcome from a simple majority would assert a
    governance rule nobody configured.
    """
    ws = _new_workspace()
    try:
        _, res = _resolution(ws)
        a = board_members.create_member("A", DIRECTOR, workspace_id=ws)
        resolutions.record_vote(res.id, a.id, VOTE_AGAINST, workspace_id=ws)

        res = resolutions.get_resolution(res.id, workspace_id=ws)
        assert resolutions.tally(res).carried is False

        # The board may still adopt against the simple-majority reading — a chair's
        # casting vote, a weighted class, a rule this system was never told.
        adopted = resolutions.transition_resolution(
            res.id, ADOPTED, expected_version=res.version, workspace_id=ws
        )
        assert adopted.status == ADOPTED
    finally:
        _cleanup(ws)


# ---------------------------------------------------------------------------
# Status machine
# ---------------------------------------------------------------------------

def test_draft_moves_to_adopted_and_stamps_adopted_at():
    ws = _new_workspace()
    try:
        _, res = _resolution(ws)
        adopted = resolutions.transition_resolution(
            res.id, ADOPTED, expected_version=res.version, workspace_id=ws
        )
        assert adopted.status == ADOPTED
        assert adopted.adopted_at is not None
    finally:
        _cleanup(ws)


def test_rejected_does_not_stamp_adopted_at():
    ws = _new_workspace()
    try:
        _, res = _resolution(ws)
        rejected = resolutions.transition_resolution(
            res.id, REJECTED, expected_version=res.version, workspace_id=ws
        )
        assert rejected.status == REJECTED
        assert rejected.adopted_at is None
    finally:
        _cleanup(ws)


@pytest.mark.parametrize("terminal", [ADOPTED, REJECTED])
def test_adopted_and_rejected_are_terminal(terminal):
    ws = _new_workspace()
    try:
        _, res = _resolution(ws)
        res = resolutions.transition_resolution(
            res.id, terminal, expected_version=res.version, workspace_id=ws
        )
        for target in (ADOPTED, REJECTED, DRAFT, SUPERSEDED):
            with pytest.raises(ResolutionLockedError):
                resolutions.transition_resolution(
                    res.id, target, expected_version=res.version, workspace_id=ws
                )
    finally:
        _cleanup(ws)


def test_an_adopted_resolution_cannot_be_edited():
    ws = _new_workspace()
    try:
        _, res = _resolution(ws)
        res = resolutions.transition_resolution(
            res.id, ADOPTED, expected_version=res.version, workspace_id=ws
        )
        with pytest.raises(ResolutionLockedError):
            resolutions.update_resolution(
                res.id, expected_version=res.version, body="rewritten", workspace_id=ws
            )
    finally:
        _cleanup(ws)


def test_unknown_status_is_rejected():
    ws = _new_workspace()
    try:
        _, res = _resolution(ws)
        with pytest.raises(ResolutionValidationError):
            resolutions.transition_resolution(
                res.id, "ratified", expected_version=res.version, workspace_id=ws
            )
    finally:
        _cleanup(ws)


# ---------------------------------------------------------------------------
# Optimistic concurrency
# ---------------------------------------------------------------------------

def test_every_mutation_is_version_guarded():
    ws = _new_workspace()
    try:
        _, res = _resolution(ws)
        stale = res.version - 1

        with pytest.raises(StaleResolutionError):
            resolutions.update_resolution(res.id, expected_version=stale, body="x", workspace_id=ws)
        with pytest.raises(StaleResolutionError):
            resolutions.transition_resolution(res.id, ADOPTED, expected_version=stale, workspace_id=ws)
        with pytest.raises(StaleResolutionError):
            resolutions.supersede_resolution(res.id, "t", "b", expected_version=stale, workspace_id=ws)
    finally:
        _cleanup(ws)


def test_recording_a_vote_bumps_the_resolution_version():
    # Otherwise a caller holding a pre-vote read could adopt the motion with a
    # version guard that no longer reflects what they saw.
    ws = _new_workspace()
    try:
        _, res = _resolution(ws)
        member = board_members.create_member("A", DIRECTOR, workspace_id=ws)
        before = res.version
        resolutions.record_vote(res.id, member.id, VOTE_FOR, workspace_id=ws)
        assert resolutions.get_resolution(res.id, workspace_id=ws).version == before + 1
    finally:
        _cleanup(ws)


# ---------------------------------------------------------------------------
# Supersession
# ---------------------------------------------------------------------------

def test_supersede_creates_a_new_version_and_freezes_the_old():
    ws = _new_workspace()
    try:
        _, res = _resolution(ws)
        res = resolutions.transition_resolution(
            res.id, ADOPTED, expected_version=res.version, workspace_id=ws
        )

        new, old = resolutions.supersede_resolution(
            res.id, "Amended", "RESOLVED THAT (as amended) …",
            expected_version=res.version, workspace_id=ws,
        )

        assert new.version_no == 2
        assert new.status == DRAFT
        assert old.status == SUPERSEDED
        assert old.superseded_by_id == new.id
        assert new.decision_id == old.decision_id
    finally:
        _cleanup(ws)


def test_supersession_does_not_carry_votes_forward():
    """Votes were cast on the old text.

    Copying them would attribute to a director a vote on wording they never saw —
    which is the difference between a versioned record and a forged one.
    """
    ws = _new_workspace()
    try:
        _, res = _resolution(ws)
        member = board_members.create_member("A", DIRECTOR, workspace_id=ws)
        resolutions.record_vote(res.id, member.id, VOTE_FOR, workspace_id=ws)

        res = resolutions.get_resolution(res.id, workspace_id=ws)
        res = resolutions.transition_resolution(
            res.id, ADOPTED, expected_version=res.version, workspace_id=ws
        )
        new, old = resolutions.supersede_resolution(
            res.id, "Amended", "new body", expected_version=res.version, workspace_id=ws
        )

        assert new.votes == []
        # The old version keeps its record intact.
        assert len(old.votes) == 1
        assert old.votes[0].vote == VOTE_FOR
    finally:
        _cleanup(ws)


def test_only_adopted_resolutions_can_be_superseded():
    ws = _new_workspace()
    try:
        _, res = _resolution(ws)
        with pytest.raises(ResolutionValidationError):
            resolutions.supersede_resolution(
                res.id, "t", "b", expected_version=res.version, workspace_id=ws
            )
    finally:
        _cleanup(ws)


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

def test_list_filters_by_decision_and_status():
    ws = _new_workspace()
    try:
        _, dec_a = _decision(ws, "Decision A")
        _, dec_b = _decision(ws, "Decision B")
        r_a = resolutions.create_resolution(dec_a.id, "R-A", "body", workspace_id=ws)
        resolutions.create_resolution(dec_b.id, "R-B", "body", workspace_id=ws)
        resolutions.transition_resolution(
            r_a.id, ADOPTED, expected_version=r_a.version, workspace_id=ws
        )

        by_decision = resolutions.list_resolutions(decision_id=dec_a.id, workspace_id=ws)
        assert [r.id for r in by_decision] == [r_a.id]

        adopted = resolutions.list_resolutions(status=ADOPTED, workspace_id=ws)
        assert [r.id for r in adopted] == [r_a.id]

        assert len(resolutions.list_resolutions(workspace_id=ws)) == 2
    finally:
        _cleanup(ws)


def test_list_rejects_an_unknown_status_filter():
    ws = _new_workspace()
    try:
        with pytest.raises(ResolutionValidationError):
            resolutions.list_resolutions(status="ratified", workspace_id=ws)
    finally:
        _cleanup(ws)


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------

def test_cross_workspace_isolation():
    ws_a, ws_b = _new_workspace(), _new_workspace()
    try:
        _, res_a = _resolution(ws_a, "Secret Resolution A")

        with pytest.raises(ResolutionNotFound):
            resolutions.get_resolution(res_a.id, workspace_id=ws_b)
        assert resolutions.list_resolutions(workspace_id=ws_b) == []
        with pytest.raises(ResolutionNotFound):
            resolutions.transition_resolution(
                res_a.id, ADOPTED, expected_version=1, workspace_id=ws_b
            )
    finally:
        _cleanup(ws_a, ws_b)


def test_a_resolution_cannot_reference_another_workspaces_decision():
    """The composite FK, asserted through the SUPERUSER connection on purpose.

    Superuser bypasses RLS, so a rejection observed there proves the CONSTRAINT is
    doing the work rather than the policy. Asserting only through `callosum_app`
    could not tell the two apart — and the p1.0.5 finding was precisely that a
    single-column FK is validated as the table owner, below the isolation boundary.
    """
    ws_a, ws_b = _new_workspace(), _new_workspace()
    try:
        _, dec_b = _decision(ws_b, "Decision in B")
        _, res_a = _resolution(ws_a)

        with psycopg.connect(settings().postgres_dsn) as conn:
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                conn.execute(
                    """
                    INSERT INTO resolution (decision_id, title, body, workspace_id)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (dec_b.id, "Cross-tenant", "body", ws_a),
                )
            conn.rollback()
    finally:
        _cleanup(ws_a, ws_b)


def test_a_vote_cannot_reference_another_workspaces_board_member():
    ws_a, ws_b = _new_workspace(), _new_workspace()
    try:
        member_b = board_members.create_member("Director B", DIRECTOR, workspace_id=ws_b)
        _, res_a = _resolution(ws_a)

        with psycopg.connect(settings().postgres_dsn) as conn:
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                conn.execute(
                    """
                    INSERT INTO resolution_vote
                        (resolution_id, board_member_id, vote, workspace_id)
                    VALUES (%s, %s, 'for', %s)
                    """,
                    (res_a.id, member_b.id, ws_a),
                )
            conn.rollback()
    finally:
        _cleanup(ws_a, ws_b)


def test_deleting_a_board_member_who_has_voted_is_refused():
    # RESTRICT, not CASCADE: the directory rule is deactivate-never-delete, so an
    # attempt to erase a member with a voting record should fail loudly rather than
    # silently remove the votes.
    ws = _new_workspace()
    try:
        _, res = _resolution(ws)
        member = board_members.create_member("A", DIRECTOR, workspace_id=ws)
        resolutions.record_vote(res.id, member.id, VOTE_FOR, workspace_id=ws)

        with psycopg.connect(settings().postgres_dsn) as conn:
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                conn.execute("DELETE FROM board_member WHERE id = %s", (member.id,))
            conn.rollback()
    finally:
        _cleanup(ws)


# ---------------------------------------------------------------------------
# A standing-recused member cannot cast a counted vote (#139)
#
# `recused` was added as a third standing state in `0012_board_member` and never
# exercised in `record_vote`. The guard tested `== "non_voting"`, so a standing-recused
# director could cast `for` and it landed in `_COUNTED_VOTES` — measured on a live
# database as part of #131, where a three-member roster reported 300% quorum.
#
# Independent of quorum policy: this is wrong data in `resolution_vote` and a wrong bar
# on /resolutions whether or not any endpoint publishes a verdict.
# ---------------------------------------------------------------------------


def test_a_standing_recused_member_cannot_cast_a_counted_vote():
    """The defect, stated directly. Fails against the previous guard."""
    ws = _new_workspace()
    try:
        _, res = _resolution(ws)
        conflicted = board_members.create_member(
            "Recused Director", DIRECTOR, voting=RECUSED, workspace_id=ws
        )

        for vote in (VOTE_FOR, VOTE_AGAINST):
            with pytest.raises(ResolutionValidationError):
                resolutions.record_vote(res.id, conflicted.id, vote, workspace_id=ws)
    finally:
        _cleanup(ws)


def test_a_standing_recused_member_cannot_abstain_either():
    """`abstain` is uncounted but not therefore permitted.

    An abstention is a deliberate choice by someone entitled to vote. A member who has
    stood down from a conflict is not choosing to abstain; recording it that way would
    put a decision in the minutes they did not make.
    """
    ws = _new_workspace()
    try:
        _, res = _resolution(ws)
        conflicted = board_members.create_member(
            "Recused Director", DIRECTOR, voting=RECUSED, workspace_id=ws
        )

        with pytest.raises(ResolutionValidationError):
            resolutions.record_vote(res.id, conflicted.id, VOTE_ABSTAIN, workspace_id=ws)
    finally:
        _cleanup(ws)


def test_a_standing_recused_member_may_still_minute_the_recusal():
    """The filter must remove the counted vote, not the member from the record.

    A resolution whose record is silent about a director cannot distinguish "recused"
    from "absent", and those are different facts in minutes.
    """
    ws = _new_workspace()
    try:
        _, res = _resolution(ws)
        conflicted = board_members.create_member(
            "Recused Director", DIRECTOR, voting=RECUSED, workspace_id=ws
        )

        recusal = resolutions.record_vote(
            res.id, conflicted.id, VOTE_RECUSED, workspace_id=ws
        )

        assert recusal.vote == VOTE_RECUSED
        assert resolutions.get_resolution(res.id, workspace_id=ws).votes[0].vote == VOTE_RECUSED
    finally:
        _cleanup(ws)


def test_the_refusal_names_which_standing_status_refused_it():
    """`non_voting` and `recused` are refused for different reasons.

    The enum exists to keep that difference (`0012_board_member`); collapsing both into
    one message would throw it away at the boundary where someone reads it.
    """
    ws = _new_workspace()
    try:
        _, res = _resolution(ws)
        observer = board_members.create_member(
            "Observer", OBSERVER, voting=NON_VOTING, workspace_id=ws
        )
        conflicted = board_members.create_member(
            "Recused Director", DIRECTOR, voting=RECUSED, workspace_id=ws
        )

        with pytest.raises(ResolutionValidationError) as observer_err:
            resolutions.record_vote(res.id, observer.id, VOTE_FOR, workspace_id=ws)
        with pytest.raises(ResolutionValidationError) as recused_err:
            resolutions.record_vote(res.id, conflicted.id, VOTE_FOR, workspace_id=ws)

        assert NON_VOTING in str(observer_err.value)
        assert RECUSED in str(recused_err.value)
        assert NON_VOTING not in str(recused_err.value)
    finally:
        _cleanup(ws)


def test_a_recused_members_vote_never_reaches_the_tally():
    """End to end: the bar on /resolutions, not just the guard.

    Two directors vote for, one recused member minutes a recusal. `carried` must rest on
    the two counted votes alone.
    """
    ws = _new_workspace()
    try:
        _, res = _resolution(ws)
        a = board_members.create_member("Director A", DIRECTOR, voting=VOTING, workspace_id=ws)
        b = board_members.create_member("Director B", DIRECTOR, voting=VOTING, workspace_id=ws)
        conflicted = board_members.create_member(
            "Recused Director", DIRECTOR, voting=RECUSED, workspace_id=ws
        )

        resolutions.record_vote(res.id, a.id, VOTE_FOR, workspace_id=ws)
        resolutions.record_vote(res.id, b.id, VOTE_FOR, workspace_id=ws)
        resolutions.record_vote(res.id, conflicted.id, VOTE_RECUSED, workspace_id=ws)

        # `tally` is pure and takes the read model, so re-fetch: `res` predates the votes.
        tally = resolutions.tally(resolutions.get_resolution(res.id, workspace_id=ws))

        assert (tally.for_, tally.against, tally.recused) == (2, 0, 1)
        # The recusal is recorded and does not weigh. `carried` resting on the two
        # counted votes is the property that matters — a guard that passes while the
        # outcome is still computed wrong would be worthless.
        assert tally.carried is True
    finally:
        _cleanup(ws)


def test_the_refused_set_is_derived_from_the_enum_not_listed():
    """Guards the fix against the shape of the bug it replaces.

    The defect was a hardcoded literal that could not know about a state added later.
    Deriving from `ALLOWED_VOTING` means a fourth standing state is excluded from casting
    until someone deliberately admits it, rather than admitted until someone remembers to
    exclude it.
    """
    assert resolutions._CANNOT_CAST == board_members.ALLOWED_VOTING - {VOTING}
    assert RECUSED in resolutions._CANNOT_CAST
    assert NON_VOTING in resolutions._CANNOT_CAST
    assert VOTING not in resolutions._CANNOT_CAST
