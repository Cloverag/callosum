"""Meeting domain — the product-domain aggregate root (Meridian P2, checkpoint 1).

This is product code, not part of the frozen engine (`src/callosum/*`). It owns the
board-meeting lifecycle; agenda items, board packs, minutes, decisions and action
items will hang off a meeting in later checkpoints.

Design contract:
  - All access goes through `store.pg(workspace_id)`, i.e. the non-superuser
    `callosum_app` role with `app.workspace_id` set, so Row-Level Security enforces
    tenant isolation for us — a read/update for the wrong workspace simply finds no
    row (raising MeetingNotFound), never another tenant's data.
  - The DB guards the allowed status SET (a CHECK in migration 0007). This module
    owns the transition RULES: which status may follow which, with `completed` and
    `cancelled` terminal.
  - Every mutation is optimistic-concurrency-guarded on `version`: the caller passes
    the version it last saw, the UPDATE matches on it and bumps it; a mismatch means
    someone else moved first -> StaleMeetingError (no row locks held).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from callosum import store
from callosum.store import DEFAULT_WORKSPACE_ID

# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

DRAFT = "draft"
SCHEDULED = "scheduled"
IN_PROGRESS = "in_progress"
COMPLETED = "completed"
CANCELLED = "cancelled"

# The allowed status set — mirrors the CHECK constraint in migration 0007.
STATUSES = frozenset({DRAFT, SCHEDULED, IN_PROGRESS, COMPLETED, CANCELLED})

# Allowed (from -> to) transitions. `completed` and `cancelled` are terminal:
# they map to the empty set, so nothing may follow them (no reopening — that would
# be a future RFC, not a silent edge here).
_TRANSITIONS: dict[str, frozenset[str]] = {
    DRAFT: frozenset({SCHEDULED, CANCELLED}),
    SCHEDULED: frozenset({IN_PROGRESS, CANCELLED}),
    IN_PROGRESS: frozenset({COMPLETED, CANCELLED}),
    COMPLETED: frozenset(),
    CANCELLED: frozenset(),
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class MeetingError(Exception):
    """Base class for meeting-domain errors."""


class MeetingNotFound(MeetingError):
    """No meeting with that id is visible in this workspace."""


class InvalidTransition(MeetingError):
    """The requested status transition is not permitted from the current status."""


class StaleMeetingError(MeetingError):
    """Optimistic-concurrency conflict: the meeting was modified since it was read."""


class MeetingValidationError(MeetingError):
    """The requested change violates a domain invariant (e.g. empty title)."""


# Importance levels (Issue #108, Meridian P6)
CRITICAL_IMPORTANCE = "critical"
HIGH_IMPORTANCE = "high"
ROUTINE_IMPORTANCE = "routine"
LOW_IMPORTANCE = "low"
IMPORTANCE_LEVELS = frozenset({CRITICAL_IMPORTANCE, HIGH_IMPORTANCE, ROUTINE_IMPORTANCE, LOW_IMPORTANCE})


# ---------------------------------------------------------------------------
# Read model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Meeting:
    id: str
    workspace_id: str
    title: str
    scheduled_start: datetime | None
    scheduled_end: datetime | None
    location: str | None
    status: str
    version: int
    created_by: str | None
    created_at: datetime
    updated_at: datetime
    importance: str = ROUTINE_IMPORTANCE


def _row_to_meeting(row: dict) -> Meeting:
    return Meeting(
        id=str(row["id"]),
        workspace_id=str(row["workspace_id"]),
        title=row["title"],
        scheduled_start=row["scheduled_start"],
        scheduled_end=row["scheduled_end"],
        location=row["location"],
        status=row["status"],
        version=row["version"],
        created_by=str(row["created_by"]) if row["created_by"] else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        importance=row.get("importance", ROUTINE_IMPORTANCE),
    )


# A sentinel distinguishing "field not provided" from an explicit `None` in updates.
_UNSET = object()


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------

def create_meeting(
    title: str,
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    scheduled_start: datetime | None = None,
    scheduled_end: datetime | None = None,
    location: str | None = None,
    created_by: str | None = None,
    importance: str = ROUTINE_IMPORTANCE,
) -> Meeting:
    """Create a meeting in `draft` status (version 1)."""
    if not title or not title.strip():
        raise MeetingValidationError("title must not be empty")
    if importance not in IMPORTANCE_LEVELS:
        raise MeetingValidationError(f"unknown importance: {importance!r}")
    if scheduled_start is not None and scheduled_end is not None:
        if scheduled_end <= scheduled_start:
            raise MeetingValidationError("scheduled_end must be after scheduled_start")
    with store.pg(workspace_id) as conn:
        row = conn.execute(
            """
            INSERT INTO meeting
                (title, scheduled_start, scheduled_end, location, created_by, workspace_id, importance)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (title.strip(), scheduled_start, scheduled_end, location, created_by, workspace_id, importance),
        ).fetchone()
    return _row_to_meeting(row)


def get_meeting(meeting_id: str, *, workspace_id: str = DEFAULT_WORKSPACE_ID) -> Meeting:
    """Fetch one meeting. Raises MeetingNotFound if it is not visible in this workspace."""
    with store.pg(workspace_id) as conn:
        row = conn.execute(
            "SELECT * FROM meeting WHERE id = %s", (uuid.UUID(str(meeting_id)),)
        ).fetchone()
    if row is None:
        raise MeetingNotFound(str(meeting_id))
    return _row_to_meeting(row)


def list_meetings(
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    status: str | None = None,
) -> list[Meeting]:
    """List meetings in the workspace, optionally filtered by status, calendar-ordered."""
    query = "SELECT * FROM meeting"
    params: list = []
    if status is not None:
        if status not in STATUSES:
            raise MeetingValidationError(f"unknown status: {status!r}")
        query += " WHERE status = %s"
        params.append(status)
    query += " ORDER BY scheduled_start NULLS LAST, created_at"
    with store.pg(workspace_id) as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_meeting(r) for r in rows]


def update_meeting(
    meeting_id: str,
    *,
    expected_version: int,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    title=_UNSET,
    scheduled_start=_UNSET,
    scheduled_end=_UNSET,
    location=_UNSET,
    importance=_UNSET,
) -> Meeting:
    """Update mutable fields under optimistic concurrency.

    Status is NOT changed here — use `transition_status`. Only the fields passed are
    updated. Raises StaleMeetingError on a version mismatch, MeetingNotFound if absent.
    """
    sets: list[str] = []
    params: list = []
    if title is not _UNSET:
        if not title or not title.strip():
            raise MeetingValidationError("title must not be empty")
        sets.append("title = %s")
        params.append(title.strip())
    if scheduled_start is not _UNSET:
        sets.append("scheduled_start = %s")
        params.append(scheduled_start)
    if scheduled_end is not _UNSET:
        sets.append("scheduled_end = %s")
        params.append(scheduled_end)
    if location is not _UNSET:
        sets.append("location = %s")
        params.append(location)
    if importance is not _UNSET:
        if importance not in IMPORTANCE_LEVELS:
            raise MeetingValidationError(f"unknown importance: {importance!r}")
        sets.append("importance = %s")
        params.append(importance)
    if not sets:
        raise MeetingValidationError("no fields to update")

    meeting_uuid = uuid.UUID(str(meeting_id))

    with store.pg(workspace_id) as conn:
        current = conn.execute(
            "SELECT status, scheduled_start, scheduled_end FROM meeting WHERE id = %s AND version = %s",
            (meeting_uuid, expected_version),
        ).fetchone()
        if current is None:
            _raise_stale_or_missing(conn, meeting_id)

        new_start = scheduled_start if scheduled_start is not _UNSET else current["scheduled_start"]
        new_end = scheduled_end if scheduled_end is not _UNSET else current["scheduled_end"]

        if new_start is not None and new_end is not None and new_end <= new_start:
            raise MeetingValidationError("scheduled_end must be after scheduled_start")

        if current["status"] in {SCHEDULED, IN_PROGRESS, COMPLETED}:
            if new_start is None or new_end is None:
                raise MeetingValidationError(
                    f"cannot clear scheduled_start or scheduled_end for meeting in status {current['status']!r}"
                )

        sets.append("version = version + 1")
        sets.append("updated_at = now()")
        params.extend([meeting_uuid, expected_version])

        row = conn.execute(
            f"UPDATE meeting SET {', '.join(sets)} WHERE id = %s AND version = %s RETURNING *",
            params,
        ).fetchone()
        if row is None:
            _raise_stale_or_missing(conn, meeting_id)
    return _row_to_meeting(row)


def transition_status(
    meeting_id: str,
    new_status: str,
    *,
    expected_version: int,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> Meeting:
    """Move a meeting to `new_status`, enforcing the lifecycle rules.

    Raises InvalidTransition for a disallowed move, StaleMeetingError on a version
    mismatch, MeetingNotFound if absent, MeetingValidationError if the target
    invariant is unmet (e.g. scheduling without a start and end).
    """
    if new_status not in STATUSES:
        raise MeetingValidationError(f"unknown status: {new_status!r}")

    with store.pg(workspace_id) as conn:
        current = conn.execute(
            "SELECT * FROM meeting WHERE id = %s", (uuid.UUID(str(meeting_id)),)
        ).fetchone()
        if current is None:
            raise MeetingNotFound(str(meeting_id))
        if current["version"] != expected_version:
            raise StaleMeetingError(
                f"meeting {meeting_id}: expected version {expected_version}, "
                f"current {current['version']}"
            )
        if new_status not in _TRANSITIONS[current["status"]]:
            raise InvalidTransition(
                f"{current['status']} -> {new_status} is not an allowed transition"
            )
        # A meeting cannot be 'scheduled' without a concrete time window.
        if new_status == SCHEDULED and (
            current["scheduled_start"] is None or current["scheduled_end"] is None
        ):
            raise MeetingValidationError(
                "cannot move to 'scheduled' without scheduled_start and scheduled_end"
            )

        row = conn.execute(
            """
            UPDATE meeting
               SET status = %s, version = version + 1, updated_at = now()
             WHERE id = %s AND version = %s
            RETURNING *
            """,
            (new_status, uuid.UUID(str(meeting_id)), expected_version),
        ).fetchone()
        # The version was just checked inside this transaction; a null row here means a
        # concurrent writer slipped in between the SELECT and UPDATE.
        if row is None:
            raise StaleMeetingError(f"meeting {meeting_id}: concurrent modification")
    return _row_to_meeting(row)


def _raise_stale_or_missing(conn, meeting_id: str) -> None:
    """A guarded UPDATE hit 0 rows: decide whether it was absent or a version mismatch."""
    exists = conn.execute(
        "SELECT version FROM meeting WHERE id = %s", (uuid.UUID(str(meeting_id)),)
    ).fetchone()
    if exists is None:
        raise MeetingNotFound(str(meeting_id))
    raise StaleMeetingError(
        f"meeting {meeting_id}: version mismatch (current {exists['version']})"
    )
