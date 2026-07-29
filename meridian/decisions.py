"""Decision domain — product-domain aggregate (Meridian P2, checkpoint 4).

This module owns formal strategic decisions and director stances. Decisions hang off a parent
Meeting aggregate and optional AgendaItem. Approved decisions are immutable historical records;
modifying an approved decision outcome requires creating a new decision via `supersede_decision`.

Design contract:
  - All database operations execute through `store.pg(workspace_id)` under `callosum_app` role,
    so Row-Level Security automatically enforces tenant isolation.
  - Allowed status set: ('proposed', 'approved', 'rejected', 'superseded', 'deferred').
  - Allowed director stances: ('SUPPORTED', 'OPPOSED', 'APPROVED', 'REQUESTED').
  - State machine: `proposed` -> `approved` | `rejected` | `deferred`. Direct status changes on
    `approved` are disallowed; an `approved` decision can only transition to `superseded` via `supersede_decision`.
  - Every update/transition/supersession is version-guarded by optimistic concurrency.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from callosum import store
from callosum.store import DEFAULT_WORKSPACE_ID
from meridian.meetings import MeetingNotFound

PROPOSED = "proposed"
APPROVED = "approved"
REJECTED = "rejected"
SUPERSEDED = "superseded"
DEFERRED = "deferred"

DECISION_STATUSES = frozenset({PROPOSED, APPROVED, REJECTED, SUPERSEDED, DEFERRED})

_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    PROPOSED: frozenset({APPROVED, REJECTED, DEFERRED}),
    APPROVED: frozenset(),  # Only exit from APPROVED is via supersede_decision -> SUPERSEDED
    REJECTED: frozenset(),
    SUPERSEDED: frozenset(),
    DEFERRED: frozenset(),
}

STANCE_SUPPORTED = "SUPPORTED"
STANCE_OPPOSED = "OPPOSED"
STANCE_APPROVED = "APPROVED"
STANCE_REQUESTED = "REQUESTED"

ALLOWED_STANCES = frozenset({STANCE_SUPPORTED, STANCE_OPPOSED, STANCE_APPROVED, STANCE_REQUESTED})

# Meeting statuses where decision creation/mutation is locked.
# Note: Diverges from agenda.py (which locks on `in_progress`) because decisions are
# recorded *during* live meetings, whereas meeting agenda structure is fixed once started.
_LOCKED_MEETING_STATUSES = frozenset({"completed", "cancelled"})

_UNSET = object()


# ---------------------------------------------------------------------------
# Typed Domain Exceptions
# ---------------------------------------------------------------------------

class DecisionError(Exception):
    """Base class for decision-domain errors."""


class DecisionNotFound(DecisionError):
    """No decision with that ID is visible in this workspace."""


class DecisionLockedError(DecisionError):
    """The decision or parent meeting is in a locked/terminal state."""


class StaleDecisionError(DecisionError):
    """Optimistic-concurrency conflict: decision was modified since it was read."""


class DecisionValidationError(DecisionError):
    """Requested change violates domain rules (e.g. empty title, invalid status/stance)."""


# ---------------------------------------------------------------------------
# Read Models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DecisionStance:
    id: str
    decision_id: str
    workspace_id: str
    person_name: str
    stance: str
    comment: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class Decision:
    id: str
    meeting_id: str
    agenda_item_id: str | None
    workspace_id: str
    title: str
    rationale: str | None
    status: str
    superseded_by_id: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    stances: list[DecisionStance]


def _row_to_stance(row: dict) -> DecisionStance:
    return DecisionStance(
        id=str(row["id"]),
        decision_id=str(row["decision_id"]),
        workspace_id=str(row["workspace_id"]),
        person_name=row["person_name"],
        stance=row["stance"],
        comment=row["comment"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_decision(row: dict, stances: list[DecisionStance] | None = None) -> Decision:
    return Decision(
        id=str(row["id"]),
        meeting_id=str(row["meeting_id"]),
        agenda_item_id=str(row["agenda_item_id"]) if row["agenda_item_id"] else None,
        workspace_id=str(row["workspace_id"]),
        title=row["title"],
        rationale=row["rationale"],
        status=row["status"],
        superseded_by_id=str(row["superseded_by_id"]) if row["superseded_by_id"] else None,
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        stances=stances or [],
    )


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _assert_meeting_active(conn, meeting_id_uuid: uuid.UUID) -> None:
    """Verifies parent meeting exists and is active (not completed/cancelled)."""
    row = conn.execute(
        "SELECT status FROM meeting WHERE id = %s FOR SHARE", (meeting_id_uuid,)
    ).fetchone()
    if row is None:
        raise MeetingNotFound(str(meeting_id_uuid))
    if row["status"] in _LOCKED_MEETING_STATUSES:
        raise DecisionLockedError(
            f"cannot modify decisions for meeting in status {row['status']!r}"
        )


def _fetch_stances_for_decisions(conn, decision_ids: list[uuid.UUID]) -> dict[str, list[DecisionStance]]:
    if not decision_ids:
        return {}
    rows = conn.execute(
        "SELECT * FROM decision_stance WHERE decision_id = ANY(%s) ORDER BY created_at ASC",
        (decision_ids,),
    ).fetchall()
    result: dict[str, list[DecisionStance]] = {}
    for r in rows:
        st = _row_to_stance(r)
        result.setdefault(st.decision_id, []).append(st)
    return result


# ---------------------------------------------------------------------------
# Public Operations
# ---------------------------------------------------------------------------

def create_decision(
    meeting_id: str,
    title: str,
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    agenda_item_id: str | None = None,
    rationale: str | None = None,
) -> Decision:
    """Creates a decision in `proposed` status attached to `meeting_id`."""
    if not title or not title.strip():
        raise DecisionValidationError("title must not be empty")

    meeting_uuid = uuid.UUID(str(meeting_id))
    agenda_uuid = uuid.UUID(str(agenda_item_id)) if agenda_item_id else None

    with store.pg(workspace_id) as conn:
        _assert_meeting_active(conn, meeting_uuid)

        if agenda_uuid:
            ag_row = conn.execute(
                "SELECT meeting_id FROM agenda_item WHERE id = %s", (agenda_uuid,)
            ).fetchone()
            if ag_row is None:
                raise DecisionValidationError(f"agenda_item {agenda_item_id} not found")
            if ag_row["meeting_id"] != meeting_uuid:
                raise DecisionValidationError(
                    f"agenda_item {agenda_item_id} does not belong to meeting {meeting_id}"
                )

        row = conn.execute(
            """
            INSERT INTO decision
                (meeting_id, agenda_item_id, title, rationale, status, workspace_id)
            VALUES (%s, %s, %s, %s, 'proposed', %s)
            RETURNING *
            """,
            (
                meeting_uuid,
                agenda_uuid,
                title.strip(),
                rationale.strip() if rationale and rationale.strip() else None,
                workspace_id,
            ),
        ).fetchone()

    return _row_to_decision(row, stances=[])


def get_decision(
    decision_id: str, *, workspace_id: str = DEFAULT_WORKSPACE_ID
) -> Decision:
    """Fetches a single decision with its director stances. Raises DecisionNotFound if missing."""
    dec_uuid = uuid.UUID(str(decision_id))
    with store.pg(workspace_id) as conn:
        row = conn.execute(
            "SELECT * FROM decision WHERE id = %s", (dec_uuid,)
        ).fetchone()
        if row is None:
            raise DecisionNotFound(str(decision_id))
        stances = _fetch_stances_for_decisions(conn, [dec_uuid]).get(str(dec_uuid), [])
    return _row_to_decision(row, stances=stances)


def list_decisions(
    meeting_id: str,
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    status: str | None = None,
) -> list[Decision]:
    """Lists all decisions for a meeting, optionally filtered by status."""
    meeting_uuid = uuid.UUID(str(meeting_id))
    query = "SELECT * FROM decision WHERE meeting_id = %s"
    params: list = [meeting_uuid]

    if status is not None:
        if status not in DECISION_STATUSES:
            raise DecisionValidationError(f"unknown decision status: {status!r}")
        query += " AND status = %s"
        params.append(status)

    query += " ORDER BY created_at ASC"

    with store.pg(workspace_id) as conn:
        rows = conn.execute(query, params).fetchall()
        dec_uuids = [r["id"] for r in rows]
        stances_map = _fetch_stances_for_decisions(conn, dec_uuids)

    return [_row_to_decision(r, stances=stances_map.get(str(r["id"]), [])) for r in rows]


def update_decision(
    decision_id: str,
    *,
    expected_version: int,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    title=_UNSET,
    rationale=_UNSET,
) -> Decision:
    """Updates title/rationale of a `proposed` decision under version concurrency.

    Only decisions in `proposed` status can be edited directly. Raises DecisionLockedError
    if the decision is already approved/rejected/superseded.
    """
    sets: list[str] = []
    params: list = []

    if title is not _UNSET:
        if not title or not title.strip():
            raise DecisionValidationError("title must not be empty")
        sets.append("title = %s")
        params.append(title.strip())

    if rationale is not _UNSET:
        sets.append("rationale = %s")
        params.append(rationale.strip() if rationale else None)

    if not sets:
        raise DecisionValidationError("no fields to update")

    dec_uuid = uuid.UUID(str(decision_id))

    with store.pg(workspace_id) as conn:
        current = conn.execute(
            "SELECT meeting_id, status, version FROM decision WHERE id = %s FOR UPDATE",
            (dec_uuid,),
        ).fetchone()

        if current is None:
            raise DecisionNotFound(str(decision_id))

        if current["version"] != expected_version:
            raise StaleDecisionError(
                f"decision {decision_id}: expected version {expected_version}, current {current['version']}"
            )

        if current["status"] != PROPOSED:
            raise DecisionLockedError(
                f"cannot update decision in status {current['status']!r}; approved decisions are immutable"
            )

        _assert_meeting_active(conn, current["meeting_id"])

        sets.append("version = version + 1")
        sets.append("updated_at = now()")
        params.extend([dec_uuid, expected_version])

        row = conn.execute(
            f"UPDATE decision SET {', '.join(sets)} WHERE id = %s AND version = %s RETURNING *",
            params,
        ).fetchone()

        if row is None:
            raise StaleDecisionError(f"decision {decision_id}: concurrent modification")

        stances = _fetch_stances_for_decisions(conn, [dec_uuid]).get(str(dec_uuid), [])

    return _row_to_decision(row, stances=stances)


def record_stance(
    decision_id: str,
    person_name: str,
    stance: str,
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    comment: str | None = None,
) -> DecisionStance:
    """Records or updates a person's stance (SUPPORTED, OPPOSED, APPROVED, REQUESTED).

    Only decisions in `proposed` status can receive stance updates. Raises DecisionLockedError
    if the decision is not in `proposed` status or if the parent meeting is inactive (completed/cancelled).
    Raises DecisionValidationError if stance/person_name is invalid, or DecisionNotFound if missing.
    """
    if not person_name or not person_name.strip():
        raise DecisionValidationError("person_name must not be empty")

    if stance not in ALLOWED_STANCES:
        raise DecisionValidationError(f"unknown stance: {stance!r}")

    dec_uuid = uuid.UUID(str(decision_id))

    with store.pg(workspace_id) as conn:
        dec = conn.execute(
            "SELECT meeting_id, status FROM decision WHERE id = %s FOR SHARE", (dec_uuid,)
        ).fetchone()

        if dec is None:
            raise DecisionNotFound(str(decision_id))

        if dec["status"] != PROPOSED:
            raise DecisionLockedError(
                f"cannot record stance for decision in status {dec['status']!r}; stances are locked on non-proposed decisions"
            )

        old_row = conn.execute(
            "SELECT stance, comment FROM decision_stance WHERE decision_id = %s AND person_name = %s",
            (dec_uuid, person_name.strip()),
        ).fetchone()

        row = conn.execute(
            """
            INSERT INTO decision_stance
                (decision_id, person_name, stance, comment, workspace_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (decision_id, person_name) DO UPDATE
               SET stance = EXCLUDED.stance,
                   comment = EXCLUDED.comment,
                   updated_at = now()
            RETURNING *
            """,
            (
                dec_uuid,
                person_name.strip(),
                stance,
                comment.strip() if comment and comment.strip() else None,
                workspace_id,
            ),
        ).fetchone()

        # Emit audit event if audit domain is available
        try:
            from meridian import audit
            audit.record_audit_event(
                conn,
                aggregate_type="decision",
                aggregate_id=dec_uuid,
                action="updated" if old_row else "created",
                payload={
                    "person_name": person_name.strip(),
                    "old_stance": old_row["stance"] if old_row else None,
                    "new_stance": stance,
                },
                workspace_id=workspace_id,
            )
        except Exception:
            pass

    return _row_to_stance(row)


def transition_decision_status(
    decision_id: str,
    new_status: str,
    *,
    expected_version: int,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> Decision:
    """Transitions decision status (e.g. proposed -> approved/rejected/deferred)."""
    if new_status not in DECISION_STATUSES:
        raise DecisionValidationError(f"unknown decision status: {new_status!r}")

    dec_uuid = uuid.UUID(str(decision_id))

    with store.pg(workspace_id) as conn:
        current = conn.execute(
            "SELECT meeting_id, status, version FROM decision WHERE id = %s FOR UPDATE",
            (dec_uuid,),
        ).fetchone()

        if current is None:
            raise DecisionNotFound(str(decision_id))

        if current["version"] != expected_version:
            raise StaleDecisionError(
                f"decision {decision_id}: expected version {expected_version}, current {current['version']}"
            )

        if new_status not in _ALLOWED_TRANSITIONS[current["status"]]:
            raise DecisionValidationError(
                f"cannot transition decision from {current['status']!r} to {new_status!r}"
            )

        _assert_meeting_active(conn, current["meeting_id"])

        row = conn.execute(
            """
            UPDATE decision
               SET status = %s, version = version + 1, updated_at = now()
             WHERE id = %s AND version = %s
            RETURNING *
            """,
            (new_status, dec_uuid, expected_version),
        ).fetchone()

        if row is None:
            raise StaleDecisionError(f"decision {decision_id}: concurrent modification")

        stances = _fetch_stances_for_decisions(conn, [dec_uuid]).get(str(dec_uuid), [])

    return _row_to_decision(row, stances=stances)


def supersede_decision(
    old_decision_id: str,
    new_title: str,
    *,
    expected_version: int,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    agenda_item_id: str | None = None,
    rationale: str | None = None,
) -> tuple[Decision, Decision]:
    """Supersedes an approved decision with a new decision.

    Marks `old_decision` as `superseded` (with `superseded_by_id = new_decision.id`) and
    creates a new decision in `proposed` status linking back to it. Returns `(new_decision, old_decision)`.
    """
    if not new_title or not new_title.strip():
        raise DecisionValidationError("new_title must not be empty")

    old_uuid = uuid.UUID(str(old_decision_id))
    agenda_uuid = uuid.UUID(str(agenda_item_id)) if agenda_item_id else None

    with store.pg(workspace_id) as conn:
        old_row = conn.execute(
            "SELECT meeting_id, status, version FROM decision WHERE id = %s FOR UPDATE",
            (old_uuid,),
        ).fetchone()

        if old_row is None:
            raise DecisionNotFound(str(old_decision_id))

        if old_row["version"] != expected_version:
            raise StaleDecisionError(
                f"decision {old_decision_id}: expected version {expected_version}, current {old_row['version']}"
            )

        if old_row["status"] != APPROVED:
            raise DecisionValidationError(
                f"only APPROVED decisions can be superseded; current status is {old_row['status']!r}"
            )

        _assert_meeting_active(conn, old_row["meeting_id"])

        if agenda_uuid:
            ag_row = conn.execute(
                "SELECT meeting_id FROM agenda_item WHERE id = %s", (agenda_uuid,)
            ).fetchone()
            if ag_row is None:
                raise DecisionValidationError(f"agenda_item {agenda_item_id} not found")
            if ag_row["meeting_id"] != old_row["meeting_id"]:
                raise DecisionValidationError(
                    f"agenda_item {agenda_item_id} does not belong to meeting {old_row['meeting_id']}"
                )

        # 1. Create the new decision first to get its UUID
        new_row = conn.execute(
            """
            INSERT INTO decision
                (meeting_id, agenda_item_id, title, rationale, status, workspace_id)
            VALUES (%s, %s, %s, %s, 'proposed', %s)
            RETURNING *
            """,
            (
                old_row["meeting_id"],
                agenda_uuid,
                new_title.strip(),
                rationale.strip() if rationale else None,
                workspace_id,
            ),
        ).fetchone()
        new_id = new_row["id"]

        # 2. Update old decision to superseded and link superseded_by_id
        updated_old = conn.execute(
            """
            UPDATE decision
               SET status = 'superseded', superseded_by_id = %s, version = version + 1, updated_at = now()
             WHERE id = %s AND version = %s
            RETURNING *
            """,
            (new_id, old_uuid, expected_version),
        ).fetchone()

        if updated_old is None:
            raise StaleDecisionError("concurrent modification during supersession")

        old_stances = _fetch_stances_for_decisions(conn, [old_uuid]).get(str(old_uuid), [])

    return _row_to_decision(new_row, stances=[]), _row_to_decision(updated_old, stances=old_stances)
