"""AgendaItem domain — product-domain aggregate (Meridian P2, checkpoint 2).

This module owns the meeting agenda lifecycle and ordering semantics. Agenda items hang off a
parent Meeting aggregate; mutations are locked once the parent meeting leaves `draft`/`scheduled`
status.

Design contract:
  - All database operations execute through `store.pg(workspace_id)` under the `callosum_app`
    role, so Row-Level Security automatically enforces tenant isolation.
  - Position is 1-indexed and strictly contiguous (1..N). Automatic position assignment appends
    to the end; explicit inserts shift subsequent items up; deletion shifts subsequent items down.
  - Reordering is atomic (`reorder_agenda_items` updates all positions in a single transaction).
    The database constraint `UNIQUE (meeting_id, position) INITIALLY DEFERRED` defers uniqueness
    checks to transaction commit, enabling seamless swaps and re-keying.
  - Parent meeting status is locked inside the same SQL transaction via `SELECT FOR SHARE`, preventing
    race conditions during status transitions.
  - Every update/delete/reorder is protected by version-guarded optimistic concurrency.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

import psycopg.errors

from callosum import store
from callosum.store import DEFAULT_WORKSPACE_ID
from meridian.meetings import MeetingNotFound

# Non-mutable meeting statuses where agenda modifications are locked
_LOCKED_MEETING_STATUSES = frozenset({"in_progress", "completed", "cancelled"})

# Sentinel object for update functions to distinguish unset arguments from explicit None
_UNSET = object()


# ---------------------------------------------------------------------------
# Typed Domain Exceptions
# ---------------------------------------------------------------------------

class AgendaItemError(Exception):
    """Base class for agenda-item domain errors."""


class AgendaItemNotFound(AgendaItemError):
    """No agenda item with that ID is visible in this workspace."""


class AgendaLockedError(AgendaItemError):
    """The parent meeting is in a non-mutable state (in_progress, completed, cancelled)."""


class StaleAgendaItemError(AgendaItemError):
    """Optimistic-concurrency conflict: item was modified since it was read."""


class AgendaItemValidationError(AgendaItemError):
    """Requested change violates domain rules (e.g. empty title, invalid duration)."""


# ---------------------------------------------------------------------------
# Read Model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AgendaItem:
    id: str
    meeting_id: str
    workspace_id: str
    title: str
    description: str | None
    duration_minutes: int | None
    presenter: str | None
    position: int
    version: int
    created_at: datetime
    updated_at: datetime


def _row_to_agenda_item(row: dict) -> AgendaItem:
    return AgendaItem(
        id=str(row["id"]),
        meeting_id=str(row["meeting_id"]),
        workspace_id=str(row["workspace_id"]),
        title=row["title"],
        description=row["description"],
        duration_minutes=row["duration_minutes"],
        presenter=row["presenter"],
        position=row["position"],
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _assert_meeting_mutable(conn, meeting_id_uuid: uuid.UUID) -> None:
    """Verifies parent meeting exists and is in a mutable status inside the active transaction."""
    row = conn.execute(
        "SELECT status FROM meeting WHERE id = %s FOR SHARE", (meeting_id_uuid,)
    ).fetchone()
    if row is None:
        raise MeetingNotFound(str(meeting_id_uuid))
    status = row["status"]
    if status in _LOCKED_MEETING_STATUSES:
        raise AgendaLockedError(
            f"cannot modify agenda for meeting in status {status!r}"
        )


# ---------------------------------------------------------------------------
# Public Operations
# ---------------------------------------------------------------------------

def create_agenda_item(
    meeting_id: str,
    title: str,
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    description: str | None = None,
    duration_minutes: str | int | None = None,
    presenter: str | None = None,
    position: int | None = None,
) -> AgendaItem:
    """Creates a new agenda item attached to `meeting_id`.

    If `position` is None, the item is appended at `max(position) + 1` (or 1 if empty).
    If `position` is explicit (1..N), existing items at position >= target are shifted up by 1.
    If `position` exceeds N + 1, it is clamped to N + 1 to preserve contiguity.
    """
    if not title or not title.strip():
        raise AgendaItemValidationError("title must not be empty")

    duration_val: int | None = None
    if duration_minutes is not None:
        try:
            duration_val = int(duration_minutes)
        except (ValueError, TypeError):
            raise AgendaItemValidationError("duration_minutes must be an integer")
        if duration_val <= 0:
            raise AgendaItemValidationError("duration_minutes must be positive")

    meeting_uuid = uuid.UUID(str(meeting_id))

    with store.pg(workspace_id) as conn:
        _assert_meeting_mutable(conn, meeting_uuid)

        # Get current max position for this meeting
        max_row = conn.execute(
            "SELECT COALESCE(MAX(position), 0) AS max_pos FROM agenda_item WHERE meeting_id = %s",
            (meeting_uuid,),
        ).fetchone()
        max_pos = max_row["max_pos"] if max_row else 0

        if position is None:
            target_pos = max_pos + 1
        elif position <= 0:
            raise AgendaItemValidationError("position must be positive")
        elif position > max_pos + 1:
            target_pos = max_pos + 1
        else:
            target_pos = position
            # Shift existing items at >= target_pos up by 1 to make room
            conn.execute(
                """
                UPDATE agenda_item
                   SET position = position + 1
                 WHERE meeting_id = %s AND position >= %s
                """,
                (meeting_uuid, target_pos),
            )

        try:
            row = conn.execute(
                """
                INSERT INTO agenda_item
                    (meeting_id, title, description, duration_minutes, presenter, position, workspace_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    meeting_uuid,
                    title.strip(),
                    description.strip() if description else None,
                    duration_val,
                    presenter.strip() if presenter else None,
                    target_pos,
                    workspace_id,
                ),
            ).fetchone()
        except psycopg.errors.UniqueViolation:
            raise AgendaItemValidationError("position collision during concurrent insert; please retry")

    return _row_to_agenda_item(row)


def get_agenda_item(
    agenda_item_id: str, *, workspace_id: str = DEFAULT_WORKSPACE_ID
) -> AgendaItem:
    """Fetches a single agenda item by ID. Raises AgendaItemNotFound if missing/invisible."""
    with store.pg(workspace_id) as conn:
        row = conn.execute(
            "SELECT * FROM agenda_item WHERE id = %s", (uuid.UUID(str(agenda_item_id)),)
        ).fetchone()
    if row is None:
        raise AgendaItemNotFound(str(agenda_item_id))
    return _row_to_agenda_item(row)


def list_agenda_items(
    meeting_id: str, *, workspace_id: str = DEFAULT_WORKSPACE_ID
) -> list[AgendaItem]:
    """Returns all agenda items for a meeting, ordered deterministically by position ASC."""
    with store.pg(workspace_id) as conn:
        rows = conn.execute(
            "SELECT * FROM agenda_item WHERE meeting_id = %s ORDER BY position ASC",
            (uuid.UUID(str(meeting_id)),),
        ).fetchall()
    return [_row_to_agenda_item(r) for r in rows]


def update_agenda_item(
    agenda_item_id: str,
    *,
    expected_version: int,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    title=_UNSET,
    description=_UNSET,
    duration_minutes=_UNSET,
    presenter=_UNSET,
) -> AgendaItem:
    """Updates mutable text and duration fields under version-guarded optimistic concurrency.

    Position updates must use `reorder_agenda_items`. Raises StaleAgendaItemError on a version
    mismatch, AgendaLockedError if parent meeting is in a non-mutable state.
    """
    sets: list[str] = []
    params: list = []

    if title is not _UNSET:
        if not title or not title.strip():
            raise AgendaItemValidationError("title must not be empty")
        sets.append("title = %s")
        params.append(title.strip())

    if description is not _UNSET:
        sets.append("description = %s")
        params.append(description.strip() if description else None)

    if duration_minutes is not _UNSET:
        if duration_minutes is None:
            sets.append("duration_minutes = %s")
            params.append(None)
        else:
            try:
                dur_val = int(duration_minutes)
            except (ValueError, TypeError):
                raise AgendaItemValidationError("duration_minutes must be an integer")
            if dur_val <= 0:
                raise AgendaItemValidationError("duration_minutes must be positive")
            sets.append("duration_minutes = %s")
            params.append(dur_val)

    if presenter is not _UNSET:
        sets.append("presenter = %s")
        params.append(presenter.strip() if presenter else None)

    if not sets:
        raise AgendaItemValidationError("no fields to update")

    item_uuid = uuid.UUID(str(agenda_item_id))

    with store.pg(workspace_id) as conn:
        # Lock item and fetch meeting_id + version
        item_row = conn.execute(
            "SELECT meeting_id, version FROM agenda_item WHERE id = %s FOR UPDATE",
            (item_uuid,),
        ).fetchone()
        if item_row is None:
            raise AgendaItemNotFound(str(agenda_item_id))
        if item_row["version"] != expected_version:
            raise StaleAgendaItemError(
                f"agenda_item {agenda_item_id}: expected version {expected_version}, "
                f"current {item_row['version']}"
            )

        # Check parent meeting mutability
        _assert_meeting_mutable(conn, item_row["meeting_id"])

        sets.append("version = version + 1")
        sets.append("updated_at = now()")
        params.extend([item_uuid, expected_version])

        row = conn.execute(
            f"UPDATE agenda_item SET {', '.join(sets)} WHERE id = %s AND version = %s RETURNING *",
            params,
        ).fetchone()
        if row is None:
            raise StaleAgendaItemError(f"agenda_item {agenda_item_id}: concurrent modification")

    return _row_to_agenda_item(row)


def delete_agenda_item(
    agenda_item_id: str,
    *,
    expected_version: int,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> None:
    """Deletes an agenda item and automatically shifts subsequent item positions down by 1.

    Raises StaleAgendaItemError on a version mismatch, AgendaLockedError if parent meeting
    is in a non-mutable status.
    """
    item_uuid = uuid.UUID(str(agenda_item_id))

    with store.pg(workspace_id) as conn:
        item_row = conn.execute(
            "SELECT meeting_id, position, version FROM agenda_item WHERE id = %s FOR UPDATE",
            (item_uuid,),
        ).fetchone()
        if item_row is None:
            raise AgendaItemNotFound(str(agenda_item_id))
        if item_row["version"] != expected_version:
            raise StaleAgendaItemError(
                f"agenda_item {agenda_item_id}: expected version {expected_version}, "
                f"current {item_row['version']}"
            )

        meeting_uuid = item_row["meeting_id"]
        deleted_pos = item_row["position"]

        _assert_meeting_mutable(conn, meeting_uuid)

        deleted = conn.execute(
            "DELETE FROM agenda_item WHERE id = %s AND version = %s RETURNING id",
            (item_uuid, expected_version),
        ).fetchone()
        if deleted is None:
            raise StaleAgendaItemError(f"agenda_item {agenda_item_id}: concurrent modification")

        # Shift items with position > deleted_pos down by 1
        conn.execute(
            """
            UPDATE agenda_item
               SET position = position - 1
             WHERE meeting_id = %s AND position > %s
            """,
            (meeting_uuid, deleted_pos),
        )


def reorder_agenda_items(
    meeting_id: str,
    ordered_item_ids: list[str],
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> list[AgendaItem]:
    """Atomically re-keys positions (1..N) according to `ordered_item_ids`.

    The list must contain exactly all item IDs belonging to the meeting.
    Uses deferred uniqueness constraint checking (`INITIALLY DEFERRED`) to perform swaps
    and reorders in a single transaction.
    """
    if not ordered_item_ids:
        raise AgendaItemValidationError("ordered_item_ids must not be empty")

    meeting_uuid = uuid.UUID(str(meeting_id))
    requested_uuids = [uuid.UUID(str(i)) for i in ordered_item_ids]

    with store.pg(workspace_id) as conn:
        _assert_meeting_mutable(conn, meeting_uuid)

        existing_rows = conn.execute(
            "SELECT id FROM agenda_item WHERE meeting_id = %s FOR UPDATE",
            (meeting_uuid,),
        ).fetchall()
        existing_uuids = {r["id"] for r in existing_rows}

        if len(set(requested_uuids)) != len(requested_uuids):
            raise AgendaItemValidationError("ordered_item_ids contains duplicate IDs")

        if set(requested_uuids) != existing_uuids or len(requested_uuids) != len(existing_uuids):
            raise AgendaItemValidationError(
                "ordered_item_ids must contain exactly all existing item IDs for the meeting"
            )

        for new_pos, item_uuid in enumerate(requested_uuids, start=1):
            conn.execute(
                """
                UPDATE agenda_item
                   SET position = %s, version = version + 1, updated_at = now()
                 WHERE id = %s
                """,
                (new_pos, item_uuid),
            )

        rows = conn.execute(
            "SELECT * FROM agenda_item WHERE meeting_id = %s ORDER BY position ASC",
            (meeting_uuid,),
        ).fetchall()

    return [_row_to_agenda_item(r) for r in rows]
