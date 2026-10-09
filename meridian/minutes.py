"""Minutes domain — product-domain aggregate (Meridian P2, checkpoint 3).

This module owns meeting minutes records. Minutes hang off a parent Meeting aggregate.

Design contract:
  - All database operations execute through `store.pg(workspace_id)` under `callosum_app` role,
    so Row-Level Security automatically enforces tenant isolation.
  - Minutes are produced *during or after* a meeting. Creation and editing are locked if the parent
    meeting is in pre-meeting status (`draft` or `scheduled`).
  - Finalised minutes are immutable. Modifying finalised minutes requires creating a new version
    via `supersede_minutes`, which increments `version_no` and links `superseded_by_id`.
  - Every mutation is guarded by optimistic concurrency (`version = version + 1`).
  - Clearance & Scoping (ADR-015, Issue #49): `minutes` records are workspace-scoped via
    Postgres Row-Level Security (`workspace_id`). Minutes document high-level formal board
    conclusions in prose and carry no `sensitivity` column or `clearance` filter argument.
    Confidential raw source materials remain strictly clearance-filtered in `board_pack_item`.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from callosum import store
from callosum.store import DEFAULT_WORKSPACE_ID
from meridian import audit
from meridian.meetings import MeetingNotFound

DRAFT = "draft"
FINAL = "final"

MINUTES_STATUSES = frozenset({DRAFT, FINAL})

# Meeting statuses where minutes creation/mutation is locked (minutes require in_progress/completed meeting)
_LOCKED_MEETING_STATUSES = frozenset({"draft", "scheduled", "cancelled"})

_UNSET = object()


# ---------------------------------------------------------------------------
# Typed Domain Exceptions
# ---------------------------------------------------------------------------

class MinutesError(Exception):
    """Base class for minutes domain errors."""


class MinutesNotFound(MinutesError):
    """No minutes record with that ID is visible in this workspace."""


class MinutesLockedError(MinutesError):
    """The minutes or parent meeting is in a locked/immutable state."""


class StaleMinutesError(MinutesError):
    """Optimistic-concurrency conflict: minutes record was modified since it was read."""


class MinutesValidationError(MinutesError):
    """Requested change violates domain rules (e.g. empty body, invalid status)."""


# ---------------------------------------------------------------------------
# Read Models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Minutes:
    id: str
    meeting_id: str
    body: str
    status: str
    version_no: int
    superseded_by_id: str | None
    finalised_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
    workspace_id: str


def _row_to_minutes(row: dict) -> Minutes:
    return Minutes(
        id=str(row["id"]),
        meeting_id=str(row["meeting_id"]),
        body=row["body"],
        status=row["status"],
        version_no=row["version_no"],
        superseded_by_id=str(row["superseded_by_id"]) if row["superseded_by_id"] else None,
        finalised_at=row["finalised_at"],
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        workspace_id=str(row["workspace_id"]),
    )


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _assert_meeting_active_or_completed(conn, meeting_id_uuid: uuid.UUID) -> None:
    """Verifies parent meeting exists and is in live/completed state (in_progress or completed)."""
    row = conn.execute(
        "SELECT status FROM meeting WHERE id = %s FOR SHARE", (meeting_id_uuid,)
    ).fetchone()
    if row is None:
        raise MeetingNotFound(str(meeting_id_uuid))
    if row["status"] in _LOCKED_MEETING_STATUSES:
        raise MinutesLockedError(
            f"cannot create or modify minutes for meeting in status {row['status']!r}; "
            f"minutes require an in_progress or completed meeting"
        )


# ---------------------------------------------------------------------------
# Public Operations
# ---------------------------------------------------------------------------

def _audit_minutes(conn, row: dict, action: str, actor_principal_id, workspace_id, **extra) -> None:
    """Records one `minutes` event inside the caller's transaction (#168).

    Shaped after `packs._audit_pack` (P5 CP5A) on purpose: same transaction as the
    mutation, called only *after* the write is confirmed, so a refusal — not found,
    stale version, locked because the minutes are final, or a parent meeting still in
    `draft` — has already raised and records nothing. `tests/test_minutes_audit.py`
    pins that for all four refusal shapes.

    **The payload deliberately does NOT carry `body`.** Minutes are the formal prose
    record of what a board was told, and `audit_event` is a different table with
    different read rules: who may read the audit trail is still open (D7, see
    ADR-016's dependency on it), so copying the text in would publish the minutes to
    a surface whose own disclosure policy has not been decided. ADR-015 is the other
    half of the reason — minutes carry no `sensitivity` column, so there is no
    clearance predicate on an audit row that would hold back a body it had copied.
    `body_chars` is carried instead: enough to see that a correction changed something
    substantial, which is the question an auditor asks of a supersession, without the
    trail becoming a second copy of the record.

    `version_no` is the lineage a supersession walks; `version` is the optimistic-
    concurrency counter and is not recorded, because it says how many times a row was
    written rather than anything about the board.
    """
    audit.record_audit_event(
        conn,
        aggregate_type="minutes",
        aggregate_id=row["id"],
        action=action,
        actor_principal_id=actor_principal_id,
        payload={
            "meeting_id": str(row["meeting_id"]),
            "status": row["status"],
            "version_no": row["version_no"],
            "body_chars": len(row["body"]),
            **extra,
        },
        workspace_id=workspace_id,
    )


def create_minutes(
    meeting_id: str,
    body: str,
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    actor_principal_id: str | None = None,
) -> Minutes:
    """Creates a draft minutes record for an in_progress or completed meeting.

    `actor_principal_id` is optional for the same reason it is in `packs.py` — the
    existing callers predate the audit write and a required argument would have been a
    26-site change to pass `None` in most of them. The API layer always supplies it,
    and `test_minutes_audit.py::test_the_route_attributes_every_minutes_event` is what
    holds that true rather than the signature.
    """
    if not body or not body.strip():
        raise MinutesValidationError("body must not be empty")

    meeting_uuid = uuid.UUID(str(meeting_id))

    with store.pg(workspace_id) as conn:
        _assert_meeting_active_or_completed(conn, meeting_uuid)

        row = conn.execute(
            """
            INSERT INTO minutes
                (meeting_id, body, status, version_no, workspace_id)
            VALUES (%s, %s, 'draft', 1, %s)
            RETURNING *
            """,
            (meeting_uuid, body.strip(), workspace_id),
        ).fetchone()

        _audit_minutes(conn, row, "created", actor_principal_id, workspace_id)

    return _row_to_minutes(row)


def get_minutes(
    minutes_id: str, *, workspace_id: str = DEFAULT_WORKSPACE_ID
) -> Minutes:
    """Fetches a single minutes record by ID. Raises MinutesNotFound if missing/invisible."""
    min_uuid = uuid.UUID(str(minutes_id))
    with store.pg(workspace_id) as conn:
        row = conn.execute(
            "SELECT * FROM minutes WHERE id = %s", (min_uuid,)
        ).fetchone()
        if row is None:
            raise MinutesNotFound(str(minutes_id))
    return _row_to_minutes(row)


def list_minutes(
    meeting_id: str,
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> list[Minutes]:
    """Returns all minutes versions for a meeting, ordered by version_no DESC."""
    meeting_uuid = uuid.UUID(str(meeting_id))
    with store.pg(workspace_id) as conn:
        rows = conn.execute(
            "SELECT * FROM minutes WHERE meeting_id = %s ORDER BY version_no DESC, created_at DESC",
            (meeting_uuid,),
        ).fetchall()
    return [_row_to_minutes(r) for r in rows]


def update_minutes(
    minutes_id: str,
    *,
    expected_version: int,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    body=_UNSET,
    actor_principal_id: str | None = None,
) -> Minutes:
    """Updates body of a draft minutes record under version-guarded optimistic concurrency."""
    if body is _UNSET:
        raise MinutesValidationError("no fields to update")

    if not body or not body.strip():
        raise MinutesValidationError("body must not be empty")

    min_uuid = uuid.UUID(str(minutes_id))

    with store.pg(workspace_id) as conn:
        current = conn.execute(
            "SELECT meeting_id, status, version FROM minutes WHERE id = %s FOR UPDATE",
            (min_uuid,),
        ).fetchone()
        if current is None:
            raise MinutesNotFound(str(minutes_id))

        if current["version"] != expected_version:
            raise StaleMinutesError(
                f"minutes {minutes_id}: expected version {expected_version}, current {current['version']}"
            )

        if current["status"] != DRAFT:
            raise MinutesLockedError(
                f"cannot update minutes in status {current['status']!r}; finalised minutes are immutable"
            )

        _assert_meeting_active_or_completed(conn, current["meeting_id"])

        row = conn.execute(
            """
            UPDATE minutes
               SET body = %s, version = version + 1, updated_at = now()
             WHERE id = %s AND version = %s
            RETURNING *
            """,
            (body.strip(), min_uuid, expected_version),
        ).fetchone()

        if row is None:
            raise StaleMinutesError(f"minutes {minutes_id}: concurrent modification")

        # `changed_fields` mirrors `packs._audit_pack`'s convention. It is a list of
        # one because `body` is the only updatable field on this aggregate; written as
        # a list anyway so a second field does not change the payload's shape.
        _audit_minutes(
            conn, row, "updated", actor_principal_id, workspace_id,
            changed_fields=["body"],
        )

    return _row_to_minutes(row)


def finalise_minutes(
    minutes_id: str,
    *,
    expected_version: int,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    actor_principal_id: str | None = None,
) -> Minutes:
    """Finalises draft minutes, locking its contents and setting finalised_at.

    Audited as `status_changed`, not `published`. Nothing is published by finalising —
    no reader gains access and nothing is sent; a draft becomes the frozen record.
    `status_changed` is the action `workspaces.revoke_membership` already uses for
    exactly this shape (a status flip on one row), and `published` is reserved for
    `packs.publish_pack`, where a pre-read genuinely becomes visible to a board.
    """
    min_uuid = uuid.UUID(str(minutes_id))

    with store.pg(workspace_id) as conn:
        current = conn.execute(
            "SELECT meeting_id, status, version FROM minutes WHERE id = %s FOR UPDATE",
            (min_uuid,),
        ).fetchone()
        if current is None:
            raise MinutesNotFound(str(minutes_id))

        if current["version"] != expected_version:
            raise StaleMinutesError(
                f"minutes {minutes_id}: expected version {expected_version}, current {current['version']}"
            )

        if current["status"] != DRAFT:
            raise MinutesValidationError(f"cannot finalise minutes in status {current['status']!r}")

        _assert_meeting_active_or_completed(conn, current["meeting_id"])

        row = conn.execute(
            """
            UPDATE minutes
               SET status = 'final', finalised_at = now(), version = version + 1, updated_at = now()
             WHERE id = %s AND version = %s
            RETURNING *
            """,
            (min_uuid, expected_version),
        ).fetchone()

        if row is None:
            raise StaleMinutesError(f"minutes {minutes_id}: concurrent modification")

        _audit_minutes(
            conn, row, "status_changed", actor_principal_id, workspace_id,
            from_status=DRAFT,
        )

    return _row_to_minutes(row)


def supersede_minutes(
    old_minutes_id: str,
    new_body: str,
    *,
    expected_version: int,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    actor_principal_id: str | None = None,
) -> tuple[Minutes, Minutes]:
    """Supersedes finalised minutes with a new draft minutes version.

    **One event, on the OLD id** — mirroring `documents.supersede_document`, which
    made the same choice so that "what replaced this?" is answerable from the
    superseded record without joining forward to a row that may itself have been
    superseded since. The payload names both ids and both `version_no`s. A second
    `created` event on the new row would say nothing the `superseded` payload does not
    already carry, and would make the pair non-atomic to read: an auditor filtering
    `action = 'created'` would see corrections and originals as the same kind of act.
    """
    if not new_body or not new_body.strip():
        raise MinutesValidationError("new_body must not be empty")

    old_uuid = uuid.UUID(str(old_minutes_id))

    with store.pg(workspace_id) as conn:
        old_row = conn.execute(
            "SELECT meeting_id, status, version, version_no FROM minutes WHERE id = %s FOR UPDATE",
            (old_uuid,),
        ).fetchone()
        if old_row is None:
            raise MinutesNotFound(str(old_minutes_id))

        if old_row["version"] != expected_version:
            raise StaleMinutesError(
                f"minutes {old_minutes_id}: expected version {expected_version}, current {old_row['version']}"
            )

        if old_row["status"] != FINAL:
            raise MinutesValidationError(
                f"only FINAL minutes can be superseded; current status is {old_row['status']!r}"
            )

        _assert_meeting_active_or_completed(conn, old_row["meeting_id"])

        # 1. Create new draft minutes with version_no + 1
        new_row = conn.execute(
            """
            INSERT INTO minutes
                (meeting_id, body, status, version_no, workspace_id)
            VALUES (%s, %s, 'draft', %s, %s)
            RETURNING *
            """,
            (
                old_row["meeting_id"],
                new_body.strip(),
                old_row["version_no"] + 1,
                workspace_id,
            ),
        ).fetchone()
        new_uuid = new_row["id"]

        # 2. Update old minutes to superseded_by_id = new_uuid
        updated_old = conn.execute(
            """
            UPDATE minutes
               SET superseded_by_id = %s, version = version + 1, updated_at = now()
             WHERE id = %s AND version = %s
            RETURNING *
            """,
            (new_uuid, old_uuid, expected_version),
        ).fetchone()

        # Symmetric with `update_minutes` and `finalise_minutes`, and deliberately kept
        # even though it cannot fire today.
        #
        # **Why it cannot fire:** the row was taken `FOR UPDATE` at the top of this
        # transaction and its `version` was compared to `expected_version` there, so
        # nothing can change it before this statement runs. The only write in between is
        # the INSERT of the replacement, which is a different row.
        #
        # **Why it is here anyway:** that argument is a property of the *lock*, not of
        # this statement. Its two siblings guard the identical `WHERE id = %s AND
        # version = %s ... RETURNING *` shape, and the asymmetry would outlive whatever
        # change moved the lock — dropping the `FOR UPDATE`, splitting the read and the
        # write across transactions, or adding a trigger on `minutes`. Without the
        # check, `_row_to_minutes(None)` raises `TypeError` at the end of the function:
        # a concurrency failure surfacing as a 500 and an internal traceback, instead of
        # the 409 the taxonomy already maps `StaleMinutesError` to.
        #
        # It raises BEFORE the audit write, so a refusal records nothing —
        # `test_minutes_audit_static.py::test_the_audit_write_is_the_last_statement_in_
        # the_transaction_body` enforces that position rather than leaving it to habit.
        if updated_old is None:
            raise StaleMinutesError(f"minutes {old_minutes_id}: concurrent modification")

        _audit_minutes(
            conn, updated_old, "superseded", actor_principal_id, workspace_id,
            new_minutes_id=str(new_uuid),
            new_version_no=new_row["version_no"],
            new_body_chars=len(new_row["body"]),
        )

    return _row_to_minutes(new_row), _row_to_minutes(updated_old)
