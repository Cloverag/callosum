"""Resolution domain — product-domain aggregate (Meridian P2, checkpoint 6).

This module owns formal resolutions and the votes cast on them. A resolution hangs off
the `Decision` that produced it.

A Decision is what the board concluded; a Resolution is the formal instrument recording
it. FR-EXEC-02 requires a draft action item, a formally adopted resolution, and an
external task to stay separable — this is the middle one.

Design contract:
  - All database operations execute through `store.pg(workspace_id)` under `callosum_app`
    role, so Row-Level Security automatically enforces tenant isolation.
  - Allowed status set: ('draft', 'adopted', 'rejected', 'superseded').
  - State machine: `draft` -> `adopted` | `rejected`. An adopted resolution is immutable;
    its only exit is `supersede_resolution`, which creates a new version and marks the old
    one `superseded`.
  - Votes may only be cast or changed while the resolution is `draft`. Once adopted or
    rejected, the voting record is frozen — a board's voting record is the evidence for the
    outcome, so it cannot be editable after the outcome is recorded.
  - Every mutation is version-guarded by optimistic concurrency (`version = version + 1`).

Legal scope: NONE. `signing_state` is a single-value enum pinned to `not_applicable`.
Nothing here asserts that a resolution is legally executed; e-signature and jurisdiction
are P8.
"""

import uuid
from typing import Any
from dataclasses import dataclass
from datetime import datetime

from callosum import store
from callosum.store import DEFAULT_WORKSPACE_ID
from meridian import board_members

DRAFT = "draft"
ADOPTED = "adopted"
REJECTED = "rejected"
SUPERSEDED = "superseded"

RESOLUTION_STATUSES = frozenset({DRAFT, ADOPTED, REJECTED, SUPERSEDED})

_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    DRAFT: frozenset({ADOPTED, REJECTED}),
    ADOPTED: frozenset(),  # Only exit is supersede_resolution -> SUPERSEDED
    REJECTED: frozenset(),
    SUPERSEDED: frozenset(),
}

VOTE_FOR = "for"
VOTE_AGAINST = "against"
VOTE_ABSTAIN = "abstain"
VOTE_RECUSED = "recused"

ALLOWED_VOTES = frozenset({VOTE_FOR, VOTE_AGAINST, VOTE_ABSTAIN, VOTE_RECUSED})

# Votes that count toward the outcome. `abstain` and `recused` are recorded but do
# not weigh: an abstention is a deliberate non-vote, and a recusal is a declared
# conflict. Counting either as opposition would misreport the board.
_COUNTED_VOTES = frozenset({VOTE_FOR, VOTE_AGAINST})

# Standing states that may not cast a counted vote — DERIVED, not listed.
#
# The bug this replaces (#139) was a hardcoded `== "non_voting"`, written when
# `voting` had the two states that mattered to its author. `recused` was already a
# third state in `0012_board_member`, and the literal could not know that.
#
# Subtracting from `ALLOWED_VOTING` inverts the failure mode: a fourth standing state
# added to the enum is excluded from casting until someone deliberately admits it,
# rather than silently admitted until someone remembers to exclude it. The enum stays
# the single source of truth for what standing statuses exist.
_CANNOT_CAST = board_members.ALLOWED_VOTING - {board_members.VOTING}

# Meeting statuses where resolution creation/mutation is locked.
#
# Matches decisions.py rather than agenda.py, and for the same reason: a resolution
# is drafted and voted on *during* a live meeting, so `in_progress` must stay open.
# It is the completed/cancelled meeting that freezes the instrument.
_LOCKED_MEETING_STATUSES = frozenset({"completed", "cancelled"})

_UNSET = object()


# ---------------------------------------------------------------------------
# Typed Domain Exceptions
# ---------------------------------------------------------------------------

class ResolutionError(Exception):
    """Base class for resolution-domain errors."""


class ResolutionNotFound(ResolutionError):
    """No resolution with that ID is visible in this workspace."""


class ResolutionLockedError(ResolutionError):
    """The resolution or its parent meeting is in a locked/terminal state."""


class StaleResolutionError(ResolutionError):
    """Optimistic-concurrency conflict: resolution was modified since it was read."""


class ResolutionValidationError(ResolutionError):
    """Requested change violates domain rules (e.g. empty body, invalid vote)."""


class DecisionNotFound(ResolutionError):
    """No decision with that ID is visible in this workspace.

    Deliberately raised for both "no such decision" and "that decision belongs to
    another workspace": the RLS-scoped read cannot see the latter, and reporting
    them differently would confirm the existence of another tenant's row.
    """


class BoardMemberNotFound(ResolutionError):
    """No board member with that ID is visible in this workspace, or they are inactive."""


# ---------------------------------------------------------------------------
# Read Models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResolutionVote:
    id: str
    resolution_id: str
    board_member_id: str
    vote: str
    created_at: datetime
    updated_at: datetime
    workspace_id: str


@dataclass(frozen=True)
class Resolution:
    id: str
    decision_id: str
    title: str
    body: str
    status: str
    signing_state: str
    version_no: int
    superseded_by_id: str | None
    adopted_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
    workspace_id: str
    votes: list[ResolutionVote]


@dataclass(frozen=True)
class VoteTally:
    """Counts by vote, plus whether the motion carried.

    `carried` is a simple majority of votes actually cast for or against, which is
    the only rule this system is entitled to apply: quorum and supermajority
    thresholds are governance policy that varies per board and per motion type, and
    the product has nowhere to record them yet. `carried` is therefore advisory —
    the authoritative outcome is `status`, which a human sets via `adopt_resolution`.
    """

    for_: int
    against: int
    abstain: int
    recused: int

    @property
    def counted(self) -> int:
        return self.for_ + self.against

    @property
    def carried(self) -> bool:
        return self.for_ > self.against


def _row_to_vote(row: dict) -> ResolutionVote:
    return ResolutionVote(
        id=str(row["id"]),
        resolution_id=str(row["resolution_id"]),
        board_member_id=str(row["board_member_id"]),
        vote=row["vote"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        workspace_id=str(row["workspace_id"]),
    )


def _row_to_resolution(row: dict, votes: list[ResolutionVote]) -> Resolution:
    return Resolution(
        id=str(row["id"]),
        decision_id=str(row["decision_id"]),
        title=row["title"],
        body=row["body"],
        status=row["status"],
        signing_state=row["signing_state"],
        version_no=row["version_no"],
        superseded_by_id=str(row["superseded_by_id"]) if row["superseded_by_id"] else None,
        adopted_at=row["adopted_at"],
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        workspace_id=str(row["workspace_id"]),
        votes=votes,
    )


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _assert_meeting_mutable(conn, decision_id_uuid: uuid.UUID) -> None:
    """Verifies the resolution's grandparent meeting is not completed or cancelled.

    Joins through `decision`. Both reads are RLS-scoped, so a decision in another
    workspace is simply not found.
    """
    row = conn.execute(
        """
        SELECT m.status
          FROM decision d
          JOIN meeting m ON m.id = d.meeting_id
         WHERE d.id = %s
         FOR SHARE OF m
        """,
        (decision_id_uuid,),
    ).fetchone()
    if row is None:
        raise DecisionNotFound(str(decision_id_uuid))
    if row["status"] in _LOCKED_MEETING_STATUSES:
        raise ResolutionLockedError(
            f"cannot modify a resolution for a meeting in status {row['status']!r}"
        )


def _fetch_votes(conn, resolution_uuids: list[uuid.UUID]) -> dict[str, list[ResolutionVote]]:
    if not resolution_uuids:
        return {}
    rows = conn.execute(
        """
        SELECT * FROM resolution_vote
         WHERE resolution_id = ANY(%s)
         ORDER BY created_at ASC
        """,
        (resolution_uuids,),
    ).fetchall()
    out: dict[str, list[ResolutionVote]] = {}
    for r in rows:
        v = _row_to_vote(r)
        out.setdefault(v.resolution_id, []).append(v)
    return out


# ---------------------------------------------------------------------------
# Public Operations
# ---------------------------------------------------------------------------

def create_resolution(
    decision_id: str,
    title: str,
    body: str,
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> Resolution:
    """Creates a draft resolution recording `decision_id`."""
    if not title or not title.strip():
        raise ResolutionValidationError("title must not be empty")
    if not body or not body.strip():
        raise ResolutionValidationError("body must not be empty")

    dec_uuid = uuid.UUID(str(decision_id))

    with store.pg(workspace_id) as conn:
        # RLS-scoped existence check. The composite FK would also reject a
        # cross-workspace decision_id, but it would surface as a ForeignKeyViolation
        # rather than a domain error, and callers should not have to catch psycopg
        # exceptions to handle a missing parent.
        dec = conn.execute("SELECT id FROM decision WHERE id = %s", (dec_uuid,)).fetchone()
        if dec is None:
            raise DecisionNotFound(str(decision_id))

        _assert_meeting_mutable(conn, dec_uuid)

        row = conn.execute(
            """
            INSERT INTO resolution
                (decision_id, title, body, status, version_no, workspace_id)
            VALUES (%s, %s, %s, 'draft', 1, %s)
            RETURNING *
            """,
            (dec_uuid, title.strip(), body.strip(), workspace_id),
        ).fetchone()

    return _row_to_resolution(row, votes=[])


def get_resolution(
    resolution_id: str, *, workspace_id: str = DEFAULT_WORKSPACE_ID
) -> Resolution:
    """Fetches a single resolution with its votes. Raises ResolutionNotFound if invisible."""
    res_uuid = uuid.UUID(str(resolution_id))
    with store.pg(workspace_id) as conn:
        row = conn.execute("SELECT * FROM resolution WHERE id = %s", (res_uuid,)).fetchone()
        if row is None:
            raise ResolutionNotFound(str(resolution_id))
        votes = _fetch_votes(conn, [res_uuid]).get(str(res_uuid), [])
    return _row_to_resolution(row, votes=votes)


def list_resolutions(
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    decision_id: str | None = None,
    status: str | None = None,
) -> list[Resolution]:
    """Returns resolutions, newest first, optionally filtered by decision or status."""
    query = "SELECT * FROM resolution WHERE true"
    params: list = []

    if decision_id is not None:
        query += " AND decision_id = %s"
        params.append(uuid.UUID(str(decision_id)))

    if status is not None:
        if status not in RESOLUTION_STATUSES:
            raise ResolutionValidationError(f"unknown resolution status: {status!r}")
        query += " AND status = %s"
        params.append(status)

    query += " ORDER BY version_no DESC, created_at DESC"

    with store.pg(workspace_id) as conn:
        rows = conn.execute(query, params).fetchall()
        votes = _fetch_votes(conn, [r["id"] for r in rows])

    return [_row_to_resolution(r, votes=votes.get(str(r["id"]), [])) for r in rows]


def update_resolution(
    resolution_id: str,
    *,
    expected_version: int,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    title=_UNSET,
    body=_UNSET,
) -> Resolution:
    """Updates the text of a `draft` resolution under optimistic concurrency."""
    if title is _UNSET and body is _UNSET:
        raise ResolutionValidationError("no fields to update")
    if title is not _UNSET and (not title or not title.strip()):
        raise ResolutionValidationError("title must not be empty")
    if body is not _UNSET and (not body or not body.strip()):
        raise ResolutionValidationError("body must not be empty")

    res_uuid = uuid.UUID(str(resolution_id))

    with store.pg(workspace_id) as conn:
        current = conn.execute(
            "SELECT decision_id, status, version FROM resolution WHERE id = %s FOR UPDATE",
            (res_uuid,),
        ).fetchone()
        if current is None:
            raise ResolutionNotFound(str(resolution_id))

        if current["version"] != expected_version:
            raise StaleResolutionError(
                f"resolution {resolution_id}: expected version {expected_version}, "
                f"current {current['version']}"
            )

        if current["status"] != DRAFT:
            raise ResolutionLockedError(
                f"cannot update a resolution in status {current['status']!r}; "
                "adopted resolutions are immutable"
            )

        _assert_meeting_mutable(conn, current["decision_id"])

        sets, params = [], []
        if title is not _UNSET:
            sets.append("title = %s")
            params.append(title.strip())
        if body is not _UNSET:
            sets.append("body = %s")
            params.append(body.strip())

        params.extend([res_uuid, expected_version])
        row = conn.execute(
            f"""
            UPDATE resolution
               SET {', '.join(sets)}, version = version + 1, updated_at = now()
             WHERE id = %s AND version = %s
            RETURNING *
            """,
            params,
        ).fetchone()

        if row is None:
            raise StaleResolutionError(f"resolution {resolution_id}: concurrent modification")

        votes = _fetch_votes(conn, [res_uuid]).get(str(res_uuid), [])

    return _row_to_resolution(row, votes=votes)


def record_vote(
    resolution_id: str,
    board_member_id: str,
    vote: str,
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> ResolutionVote:
    """Records or changes a board member's vote on a `draft` resolution.

    Only `draft` resolutions accept votes. Once a resolution is adopted or rejected the
    voting record is frozen — it is the evidence for the outcome, so allowing it to
    change afterwards would let the record contradict the result it produced. This is
    the `record_stance` finding from the CP4 review, applied here from the start.
    """
    if vote not in ALLOWED_VOTES:
        raise ResolutionValidationError(f"unknown vote: {vote!r}")

    res_uuid = uuid.UUID(str(resolution_id))
    member_uuid = uuid.UUID(str(board_member_id))

    with store.pg(workspace_id) as conn:
        res = conn.execute(
            "SELECT decision_id, status FROM resolution WHERE id = %s FOR SHARE",
            (res_uuid,),
        ).fetchone()
        if res is None:
            raise ResolutionNotFound(str(resolution_id))

        if res["status"] != DRAFT:
            raise ResolutionLockedError(
                f"cannot record a vote on a resolution in status {res['status']!r}; "
                "the voting record is frozen once the outcome is recorded"
            )

        _assert_meeting_mutable(conn, res["decision_id"])

        member = conn.execute(
            "SELECT voting, active FROM board_member WHERE id = %s", (member_uuid,)
        ).fetchone()
        if member is None or not member["active"]:
            # Inactive is conflated with absent on purpose: both mean "not eligible
            # to vote here", and distinguishing them tells a caller that a member
            # exists in a workspace whose directory they may not be reading.
            raise BoardMemberNotFound(str(board_member_id))

        # Two standing states cannot cast a counted vote, for different reasons, and
        # `board_member.voting` is an enum rather than a boolean precisely so the
        # difference survives (`0012_board_member.py`). `non_voting` is an observer or
        # adviser who never had a vote; `recused` is a director who has one in principle
        # and stands down from a persistent conflict.
        #
        # `recused` was missing here, so a standing-recused director could cast `for` and
        # it landed in `_COUNTED_VOTES` — wrong data in the table and a wrong bar on
        # /resolutions, independent of any quorum policy (#139).
        #
        # Both may still record VOTE_RECUSED. That is not a formality: a resolution whose
        # record is silent about a director cannot distinguish "recused" from "absent",
        # and those are different facts in minutes.
        if member["voting"] in _CANNOT_CAST and vote != VOTE_RECUSED:
            raise ResolutionValidationError(
                f"board member {board_member_id} is {member['voting']} and cannot cast "
                f"{vote!r}; only {VOTE_RECUSED!r} may be recorded for a standing "
                f"{member['voting']} member"
            )

        row = conn.execute(
            """
            INSERT INTO resolution_vote
                (resolution_id, board_member_id, vote, workspace_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (resolution_id, board_member_id) DO UPDATE
                SET vote = EXCLUDED.vote, updated_at = now()
            RETURNING *
            """,
            (res_uuid, member_uuid, vote, workspace_id),
        ).fetchone()

        # `created_at` is deliberately absent from the DO UPDATE list: it records
        # when this member first voted on this motion, which is audit history.
        conn.execute(
            "UPDATE resolution SET version = version + 1, updated_at = now() WHERE id = %s",
            (res_uuid,),
        )

        from meridian import audit
        audit.record_audit_event(
            conn,
            aggregate_type="resolution",
            aggregate_id=res_uuid,
            action="voted",
            payload={"board_member_id": str(member_uuid), "vote": vote},
            workspace_id=workspace_id,
        )

    return _row_to_vote(row)


def tally(resolution: Resolution) -> VoteTally:
    """Counts the votes on a resolution. Pure — takes a read model, touches no database."""
    counts = {v: 0 for v in ALLOWED_VOTES}
    for v in resolution.votes:
        counts[v.vote] += 1
    return VoteTally(
        for_=counts[VOTE_FOR],
        against=counts[VOTE_AGAINST],
        abstain=counts[VOTE_ABSTAIN],
        recused=counts[VOTE_RECUSED],
    )


def transition_resolution(
    resolution_id: str,
    new_status: str,
    *,
    expected_version: int,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> Resolution:
    """Moves a `draft` resolution to `adopted` or `rejected`.

    The outcome is set by a human, not derived from the tally. `VoteTally.carried` is
    advisory: quorum and supermajority rules vary per board and this system has nowhere
    to record them, so inferring the outcome from a simple majority would be asserting a
    governance rule the product was never told.
    """
    if new_status not in RESOLUTION_STATUSES:
        raise ResolutionValidationError(f"unknown resolution status: {new_status!r}")

    res_uuid = uuid.UUID(str(resolution_id))

    with store.pg(workspace_id) as conn:
        current = conn.execute(
            "SELECT decision_id, status, version FROM resolution WHERE id = %s FOR UPDATE",
            (res_uuid,),
        ).fetchone()
        if current is None:
            raise ResolutionNotFound(str(resolution_id))

        if current["version"] != expected_version:
            raise StaleResolutionError(
                f"resolution {resolution_id}: expected version {expected_version}, "
                f"current {current['version']}"
            )

        allowed = _ALLOWED_TRANSITIONS[current["status"]]
        if new_status not in allowed:
            raise ResolutionLockedError(
                f"cannot move a resolution from {current['status']!r} to {new_status!r}"
            )

        _assert_meeting_mutable(conn, current["decision_id"])

        row = conn.execute(
            """
            UPDATE resolution
               SET status = %s,
                   adopted_at = CASE WHEN %s = 'adopted' THEN now() ELSE adopted_at END,
                   version = version + 1,
                   updated_at = now()
             WHERE id = %s AND version = %s
            RETURNING *
            """,
            (new_status, new_status, res_uuid, expected_version),
        ).fetchone()

        if row is None:
            raise StaleResolutionError(f"resolution {resolution_id}: concurrent modification")

        votes = _fetch_votes(conn, [res_uuid]).get(str(res_uuid), [])

    return _row_to_resolution(row, votes=votes)


def supersede_resolution(
    old_resolution_id: str,
    new_title: str,
    new_body: str,
    *,
    expected_version: int,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> tuple[Resolution, Resolution]:
    """Amends an adopted resolution by creating a new draft version.

    Returns `(new, old)`. Votes are NOT copied: they were cast on the old text, and
    carrying them forward would attribute to a director a vote on wording they never
    saw. The new version starts unvoted.
    """
    if not new_title or not new_title.strip():
        raise ResolutionValidationError("new_title must not be empty")
    if not new_body or not new_body.strip():
        raise ResolutionValidationError("new_body must not be empty")

    old_uuid = uuid.UUID(str(old_resolution_id))

    with store.pg(workspace_id) as conn:
        old = conn.execute(
            """
            SELECT decision_id, status, version, version_no
              FROM resolution WHERE id = %s FOR UPDATE
            """,
            (old_uuid,),
        ).fetchone()
        if old is None:
            raise ResolutionNotFound(str(old_resolution_id))

        if old["version"] != expected_version:
            raise StaleResolutionError(
                f"resolution {old_resolution_id}: expected version {expected_version}, "
                f"current {old['version']}"
            )

        if old["status"] != ADOPTED:
            raise ResolutionValidationError(
                f"only ADOPTED resolutions can be superseded; current status is {old['status']!r}"
            )

        _assert_meeting_mutable(conn, old["decision_id"])

        new_row = conn.execute(
            """
            INSERT INTO resolution
                (decision_id, title, body, status, version_no, workspace_id)
            VALUES (%s, %s, %s, 'draft', %s, %s)
            RETURNING *
            """,
            (
                old["decision_id"],
                new_title.strip(),
                new_body.strip(),
                old["version_no"] + 1,
                workspace_id,
            ),
        ).fetchone()

        updated_old = conn.execute(
            """
            UPDATE resolution
               SET status = 'superseded',
                   superseded_by_id = %s,
                   version = version + 1,
                   updated_at = now()
             WHERE id = %s AND version = %s
            RETURNING *
            """,
            (new_row["id"], old_uuid, expected_version),
        ).fetchone()

        if updated_old is None:
            raise StaleResolutionError(
                f"resolution {old_resolution_id}: concurrent modification"
            )

        old_votes = _fetch_votes(conn, [old_uuid]).get(str(old_uuid), [])

    return (
        _row_to_resolution(new_row, votes=[]),
        _row_to_resolution(updated_old, votes=old_votes),
    )


# ---------------------------------------------------------------------------
# Policy Evaluation Engine & Commitment Bridge (Issue #93, Meridian P3 CP-F/G/H)
# ---------------------------------------------------------------------------

POLICY_SIMPLE_MAJORITY = "simple_majority"
POLICY_SUPERMAJORITY_TWOTHIRDS = "supermajority_twothirds"
POLICY_UNANIMOUS = "unanimous"

SUPPORTED_POLICIES = frozenset({
    POLICY_SIMPLE_MAJORITY,
    POLICY_SUPERMAJORITY_TWOTHIRDS,
    POLICY_UNANIMOUS,
})


def evaluate_resolution_policy(
    resolution: Resolution,
    total_voting_members: int,
    *,
    policy_type: str = POLICY_SIMPLE_MAJORITY,
    quorum_percent: float = 50.0,
) -> dict[str, Any]:
    """Evaluates voting quorum and policy thresholds for a resolution motion."""
    if policy_type not in SUPPORTED_POLICIES:
        raise ResolutionValidationError(f"unknown policy_type: {policy_type!r}")
    if total_voting_members <= 0:
        raise ResolutionValidationError("total_voting_members must be > 0")

    t = tally(resolution)
    total_participants = t.for_ + t.against + t.abstain + t.recused
    actual_quorum_pct = (total_participants / float(total_voting_members)) * 100.0
    quorum_met = actual_quorum_pct >= quorum_percent

    threshold_passed = False
    if policy_type == POLICY_SIMPLE_MAJORITY:
        threshold_passed = t.for_ > t.against
    elif policy_type == POLICY_SUPERMAJORITY_TWOTHIRDS:
        threshold_passed = t.counted > 0 and ((t.for_ / float(t.counted)) >= (2.0 / 3.0))
    elif policy_type == POLICY_UNANIMOUS:
        threshold_passed = t.for_ > 0 and t.against == 0 and t.abstain == 0

    return {
        "resolution_id": resolution.id,
        "policy_type": policy_type,
        "quorum_percent_required": quorum_percent,
        "quorum_percent_actual": round(actual_quorum_pct, 2),
        "quorum_met": quorum_met,
        "threshold_passed": threshold_passed,
        "passed": quorum_met and threshold_passed,
        "tally": {
            "for": t.for_,
            "against": t.against,
            "abstain": t.abstain,
            "recused": t.recused,
            "counted": t.counted,
        },
    }


def bridge_resolution_to_commitment(
    resolution_id: str,
    owner_board_member_id: str,
    *,
    due_date: datetime | None = None,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> Any:
    """Converts an ADOPTED resolution into an actionable Commitment linked to the Decision."""
    res_uuid = uuid.UUID(str(resolution_id))
    with store.pg(workspace_id) as conn:
        res = conn.execute(
            "SELECT decision_id, title, status FROM resolution WHERE id = %s",
            (res_uuid,),
        ).fetchone()
        if res is None:
            raise ResolutionNotFound(str(resolution_id))
        if res["status"] != ADOPTED:
            raise ResolutionValidationError(
                f"only ADOPTED resolutions can be converted into commitments; current status is {res['status']!r}"
            )
        decision_id = str(res["decision_id"])

    from meridian import commitments
    commitment = commitments.create_commitment(
        title=res["title"],
        owner_board_member_id=owner_board_member_id,
        decision_id=decision_id,
        due_date=due_date,
        workspace_id=workspace_id,
    )

    with store.pg(workspace_id) as conn:
        from meridian import audit
        audit.record_audit_event(
            conn,
            aggregate_type="resolution",
            aggregate_id=res_uuid,
            action="status_changed",
            payload={"commitment_id": commitment.id, "owner_id": owner_board_member_id, "detail": "resolution_bridged_to_commitment"},
            workspace_id=workspace_id,
        )

    return commitment

