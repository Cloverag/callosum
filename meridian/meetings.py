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

import psycopg

from callosum import store
from callosum.store import DEFAULT_WORKSPACE_ID
from meridian import audit
from meridian.documents import Document

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


# ---------------------------------------------------------------------------
# Material — documents assigned to a meeting (Meridian P4, ADR-018)
# ---------------------------------------------------------------------------

class MaterialError(MeetingError):
    """Base class for meeting-material errors."""


class MaterialAlreadyAssignedError(MaterialError):
    """This document is already material for this meeting."""


class MaterialNotAssignedError(MaterialError):
    """This document is not material for this meeting."""


@dataclass(frozen=True)
class MeetingMaterial:
    """What one caller may see of a meeting's material, and how many they may not.

    **The count is disclosed (ADR-018), and it is the only thing disclosed.** Material
    assigned to a meeting claims to be *the material for this meeting*, which is a
    completeness claim: a director who prepares from a list that silently dropped two
    contracts walks into the room believing they are prepared. That is the same harm
    `documents.version_chain` exists to prevent, one object over.

    `withheld` is a count and never a title, an id, a date, a doc_type or a position.
    """

    documents: list[Document]
    withheld: int


def assign_material(
    meeting_id: str,
    document_id: str,
    *,
    clearance: int,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    actor_principal_id: str | None = None,
    assigned_by: str | None = None,
) -> None:
    """Record that a document is material for a meeting.

    **A document the caller cannot read answers `MeetingNotFound`, not a permission
    error.** The refusal deliberately does not distinguish "no such document" from "above
    your clearance": telling the two apart turns this endpoint into an existence oracle,
    and document ids are derivable from candidate plaintext
    (`documents._document_id` is `uuid5` over a public namespace constant), so a holder of
    a leaked memo could confirm the board holds it without reading anything. Same reason
    `documents.supersede_document` answers 404 rather than 403 for its predecessor.

    The meeting is checked first and identically, so the two refusals are indistinguishable
    from outside — one exception type, one message shape, whichever half was the problem.
    """
    ws_uuid = uuid.UUID(str(workspace_id))
    meeting_uuid = uuid.UUID(str(meeting_id))
    doc_uuid = uuid.UUID(str(document_id))

    with store.pg(str(ws_uuid)) as conn:
        readable = conn.execute(
            """
            SELECT (SELECT count(*) FROM meeting m WHERE m.id = %s)                    AS meeting,
                   (SELECT count(*) FROM document d WHERE d.id = %s AND d.sensitivity <= %s) AS doc
            """,
            (meeting_uuid, doc_uuid, clearance),
        ).fetchone()
        if not readable["meeting"] or not readable["doc"]:
            raise MeetingNotFound(str(meeting_id))

        try:
            conn.execute(
                """
                INSERT INTO meeting_document (workspace_id, meeting_id, document_id, assigned_by)
                VALUES (%s, %s, %s, %s)
                """,
                (ws_uuid, meeting_uuid, doc_uuid, uuid.UUID(str(assigned_by)) if assigned_by else None),
            )
        except psycopg.errors.UniqueViolation as exc:
            # `uq_meeting_document`. Raised rather than swallowed as idempotent: the
            # caller asked to add material and something already claims that fact, which
            # they should see rather than have quietly absorbed.
            raise MaterialAlreadyAssignedError(str(document_id)) from exc

        audit.record_audit_event(
            conn,
            aggregate_type="meeting",
            aggregate_id=meeting_uuid,
            action="item_added",
            actor_principal_id=actor_principal_id,
            payload={"document_id": str(doc_uuid), "kind": "material"},
            workspace_id=str(ws_uuid),
        )


def unassign_material(
    meeting_id: str,
    document_id: str,
    *,
    clearance: int,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    actor_principal_id: str | None = None,
) -> None:
    """Remove a document from a meeting's material.

    Clearance-gated on the DELETE itself, not only on a prior read: a caller who cannot
    read the document cannot remove it either, or an investor could quietly strip a
    confidential contract out of the board's material for a meeting without ever being
    able to see what they removed.
    """
    ws_uuid = uuid.UUID(str(workspace_id))
    meeting_uuid = uuid.UUID(str(meeting_id))
    doc_uuid = uuid.UUID(str(document_id))

    with store.pg(str(ws_uuid)) as conn:
        deleted = conn.execute(
            """
            DELETE FROM meeting_document md
             USING document d
             WHERE md.meeting_id = %s
               AND md.document_id = %s
               AND d.id = md.document_id
               AND d.workspace_id = md.workspace_id
               AND d.sensitivity <= %s
            RETURNING md.id
            """,
            (meeting_uuid, doc_uuid, clearance),
        ).fetchone()
        if deleted is None:
            raise MaterialNotAssignedError(str(document_id))

        audit.record_audit_event(
            conn,
            aggregate_type="meeting",
            aggregate_id=meeting_uuid,
            action="item_removed",
            actor_principal_id=actor_principal_id,
            payload={"document_id": str(doc_uuid), "kind": "material"},
            workspace_id=str(ws_uuid),
        )


def meeting_material(
    meeting_id: str,
    *,
    clearance: int,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> MeetingMaterial:
    """A meeting's material: what this caller may read, and how many they may not.

    Two queries, and the second returns only a number. The count cannot come from the
    first — rows above clearance are removed by its WHERE clause before anything could
    count them, and widening that clause to include them would put restricted titles on
    the wire, which Invariant #1 forbids. So the complement is aggregated in the database.
    `packs._fetch_items_for_packs` does the same, and both follow
    `callosum.retrieve.vector_search`, which runs its search twice for exactly this reason.

    The document projection is `documents._DOCUMENT_SELECT`, reused rather than rewritten,
    so the per-caller `superseded_by_id` redaction that `0024` needed applies here too. A
    second hand-rolled SELECT is how that redaction would come to exist on one surface and
    not the other — which is the defect it was introduced to fix.
    """
    from meridian import documents  # local: documents imports nothing from meetings

    ws_uuid = uuid.UUID(str(workspace_id))
    meeting_uuid = uuid.UUID(str(meeting_id))

    with store.pg(str(ws_uuid)) as conn:
        if conn.execute("SELECT 1 FROM meeting WHERE id = %s", (meeting_uuid,)).fetchone() is None:
            raise MeetingNotFound(str(meeting_id))

        rows = conn.execute(
            documents._DOCUMENT_SELECT
            + """
             JOIN meeting_document md
               ON md.document_id = d.id AND md.workspace_id = d.workspace_id
            WHERE md.meeting_id = %s AND d.sensitivity <= %s
            ORDER BY md.assigned_at ASC, d.id
            """,
            (clearance, meeting_uuid, clearance),
        ).fetchall()

        withheld = conn.execute(
            """
            SELECT count(*) AS withheld
              FROM meeting_document md
              JOIN document d ON d.id = md.document_id AND d.workspace_id = md.workspace_id
             WHERE md.meeting_id = %s AND d.sensitivity > %s
            """,
            (meeting_uuid, clearance),
        ).fetchone()["withheld"]

    return MeetingMaterial(
        documents=[documents._row_to_document(r) for r in rows],
        withheld=withheld,
    )
