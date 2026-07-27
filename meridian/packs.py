"""BoardPack domain — product-domain aggregate (Meridian P2, checkpoint 3).

This module owns board pack pre-read packages and their ordered document items. Board packs hang
off a parent Meeting aggregate.

Design contract:
  - All database operations execute through `store.pg(workspace_id)` under `callosum_app` role,
    so Row-Level Security automatically enforces tenant isolation.
  - Board packs are prepared *before* a meeting. Creation, editing, and item mutations are locked
    once the meeting enters `in_progress`, `completed`, or `cancelled` status.
  - Published board packs are immutable. Modifying a published pack requires creating a new version
    via `supersede_pack`, which increments `version_no` and links `superseded_by_id`.
  - Item position is 1-indexed and strictly contiguous (1..N).
  - Every mutation is guarded by optimistic concurrency (`version = version + 1`).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from callosum import store
from callosum.store import DEFAULT_WORKSPACE_ID
from meridian.meetings import MeetingNotFound

PUBLIC_CLEARANCE = 1
RESTRICTED_CLEARANCE = 4

DRAFT = "draft"
PUBLISHED = "published"

PACK_STATUSES = frozenset({DRAFT, PUBLISHED})

# Meeting statuses where board pack creation/mutation is locked
_LOCKED_MEETING_STATUSES = frozenset({"in_progress", "completed", "cancelled"})

_UNSET = object()


# ---------------------------------------------------------------------------
# Typed Domain Exceptions
# ---------------------------------------------------------------------------

class BoardPackError(Exception):
    """Base class for board-pack domain errors."""


class BoardPackNotFound(BoardPackError):
    """No board pack with that ID is visible in this workspace."""


class BoardPackLockedError(BoardPackError):
    """The parent meeting or board pack is in a non-mutable state."""


class StaleBoardPackError(BoardPackError):
    """Optimistic-concurrency conflict: pack was modified since it was read."""


class BoardPackValidationError(BoardPackError):
    """Requested change violates domain rules (e.g. empty title, invalid status)."""


# ---------------------------------------------------------------------------
# Read Model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BoardPackItem:
    id: str
    board_pack_id: str
    document_id: str
    agenda_item_id: str | None
    position: int
    note: str | None
    created_at: datetime
    workspace_id: str


@dataclass(frozen=True)
class BoardPack:
    id: str
    meeting_id: str
    title: str
    status: str
    version_no: int
    superseded_by_id: str | None
    published_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
    workspace_id: str
    items: list[BoardPackItem]


def _row_to_board_pack(row: dict, items: list[BoardPackItem]) -> BoardPack:
    return BoardPack(
        id=str(row["id"]),
        meeting_id=str(row["meeting_id"]),
        title=row["title"],
        status=row["status"],
        version_no=row["version_no"],
        superseded_by_id=str(row["superseded_by_id"]) if row["superseded_by_id"] else None,
        published_at=row["published_at"],
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        workspace_id=str(row["workspace_id"]),
        items=items,
    )


def _row_to_pack_item(row: dict) -> BoardPackItem:
    return BoardPackItem(
        id=str(row["id"]),
        board_pack_id=str(row["board_pack_id"]),
        document_id=str(row["document_id"]),
        agenda_item_id=str(row["agenda_item_id"]) if row["agenda_item_id"] else None,
        position=row["position"],
        note=row["note"],
        created_at=row["created_at"],
        workspace_id=str(row["workspace_id"]),
    )


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _assert_meeting_pre_meeting(conn, meeting_id_uuid: uuid.UUID) -> None:
    """Verifies parent meeting exists and is in pre-meeting state (draft or scheduled)."""
    row = conn.execute(
        "SELECT status FROM meeting WHERE id = %s FOR SHARE", (meeting_id_uuid,)
    ).fetchone()
    if row is None:
        raise MeetingNotFound(str(meeting_id_uuid))
    if row["status"] in _LOCKED_MEETING_STATUSES:
        raise BoardPackLockedError(
            f"cannot modify board pack for meeting in status {row['status']!r}"
        )


def _fetch_items_for_packs(
    conn, pack_ids: list[uuid.UUID], clearance: int
) -> dict[str, list[BoardPackItem]]:
    if not pack_ids:
        return {}
    rows = conn.execute(
        """
        SELECT bpi.*
          FROM board_pack_item bpi
          JOIN document d ON d.id = bpi.document_id
         WHERE bpi.board_pack_id = ANY(%s)
           AND d.sensitivity <= %s
         ORDER BY bpi.position ASC
        """,
        (pack_ids, clearance),
    ).fetchall()
    result: dict[str, list[BoardPackItem]] = {}
    for r in rows:
        it = _row_to_pack_item(r)
        result.setdefault(it.board_pack_id, []).append(it)
    return result


# ---------------------------------------------------------------------------
# Public Operations
# ---------------------------------------------------------------------------

def create_pack(
    meeting_id: str,
    title: str,
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> BoardPack:
    """Creates a new draft board pack attached to `meeting_id`."""
    if not title or not title.strip():
        raise BoardPackValidationError("title must not be empty")

    meeting_uuid = uuid.UUID(str(meeting_id))

    with store.pg(workspace_id) as conn:
        _assert_meeting_pre_meeting(conn, meeting_uuid)

        row = conn.execute(
            """
            INSERT INTO board_pack
                (meeting_id, title, status, version_no, workspace_id)
            VALUES (%s, %s, 'draft', 1, %s)
            RETURNING *
            """,
            (meeting_uuid, title.strip(), workspace_id),
        ).fetchone()

    return _row_to_board_pack(row, items=[])


def get_pack(
    pack_id: str,
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    clearance: int,
) -> BoardPack:
    """Fetches a single board pack with items filtered by caller clearance level. Raises BoardPackNotFound if missing/invisible."""
    pack_uuid = uuid.UUID(str(pack_id))
    with store.pg(workspace_id) as conn:
        row = conn.execute(
            "SELECT * FROM board_pack WHERE id = %s", (pack_uuid,)
        ).fetchone()
        if row is None:
            raise BoardPackNotFound(str(pack_id))
        items = _fetch_items_for_packs(conn, [pack_uuid], clearance=clearance).get(str(pack_uuid), [])
    return _row_to_board_pack(row, items=items)


def list_packs(
    meeting_id: str,
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    status: str | None = None,
    clearance: int,
) -> list[BoardPack]:
    """Returns all board packs for a meeting, ordered by version_no DESC, with items filtered by clearance."""
    meeting_uuid = uuid.UUID(str(meeting_id))
    query = "SELECT * FROM board_pack WHERE meeting_id = %s"
    params: list = [meeting_uuid]

    if status is not None:
        if status not in PACK_STATUSES:
            raise BoardPackValidationError(f"unknown board pack status: {status!r}")
        query += " AND status = %s"
        params.append(status)

    query += " ORDER BY version_no DESC, created_at DESC"

    with store.pg(workspace_id) as conn:
        rows = conn.execute(query, params).fetchall()
        pack_uuids = [r["id"] for r in rows]
        items_map = _fetch_items_for_packs(conn, pack_uuids, clearance=clearance)

    return [_row_to_board_pack(r, items=items_map.get(str(r["id"]), [])) for r in rows]


def update_pack(
    pack_id: str,
    *,
    expected_version: int,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    title=_UNSET,
    clearance: int,
) -> BoardPack:
    """Updates title of a `draft` board pack under version-guarded optimistic concurrency."""
    if title is _UNSET:
        raise BoardPackValidationError("no fields to update")

    if not title or not title.strip():
        raise BoardPackValidationError("title must not be empty")

    pack_uuid = uuid.UUID(str(pack_id))

    with store.pg(workspace_id) as conn:
        current = conn.execute(
            "SELECT meeting_id, status, version FROM board_pack WHERE id = %s FOR UPDATE",
            (pack_uuid,),
        ).fetchone()
        if current is None:
            raise BoardPackNotFound(str(pack_id))

        if current["version"] != expected_version:
            raise StaleBoardPackError(
                f"board_pack {pack_id}: expected version {expected_version}, current {current['version']}"
            )

        if current["status"] != DRAFT:
            raise BoardPackLockedError(
                f"cannot update board pack in status {current['status']!r}; published packs are immutable"
            )

        _assert_meeting_pre_meeting(conn, current["meeting_id"])

        row = conn.execute(
            """
            UPDATE board_pack
               SET title = %s, version = version + 1, updated_at = now()
             WHERE id = %s AND version = %s
            RETURNING *
            """,
            (title.strip(), pack_uuid, expected_version),
        ).fetchone()

        if row is None:
            raise StaleBoardPackError(f"board_pack {pack_id}: concurrent modification")

        items = _fetch_items_for_packs(conn, [pack_uuid], clearance=clearance).get(str(pack_uuid), [])

    return _row_to_board_pack(row, items=items)


def add_pack_item(
    pack_id: str,
    document_id: str,
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    agenda_item_id: str | None = None,
    position: int | None = None,
    note: str | None = None,
) -> BoardPackItem:
    """Adds a document item to a draft board pack."""
    pack_uuid = uuid.UUID(str(pack_id))
    doc_uuid = uuid.UUID(str(document_id))
    ag_uuid = uuid.UUID(str(agenda_item_id)) if agenda_item_id else None

    with store.pg(workspace_id) as conn:
        pack = conn.execute(
            "SELECT meeting_id, status FROM board_pack WHERE id = %s FOR UPDATE",
            (pack_uuid,),
        ).fetchone()
        if pack is None:
            raise BoardPackNotFound(str(pack_id))

        if pack["status"] != DRAFT:
            raise BoardPackLockedError(
                f"cannot add items to board pack in status {pack['status']!r}; published packs are immutable"
            )

        _assert_meeting_pre_meeting(conn, pack["meeting_id"])

        # Validate document exists
        doc = conn.execute(
            "SELECT id FROM document WHERE id = %s", (doc_uuid,)
        ).fetchone()
        if doc is None:
            raise BoardPackValidationError(f"document {document_id} not found")

        # Check duplicate document
        dup = conn.execute(
            "SELECT id FROM board_pack_item WHERE board_pack_id = %s AND document_id = %s",
            (pack_uuid, doc_uuid),
        ).fetchone()
        if dup is not None:
            raise BoardPackValidationError(
                f"document {document_id} is already in board_pack {pack_id}"
            )

        # Validate agenda_item if provided
        if ag_uuid:
            ag = conn.execute(
                "SELECT meeting_id FROM agenda_item WHERE id = %s", (ag_uuid,)
            ).fetchone()
            if ag is None or ag["meeting_id"] != pack["meeting_id"]:
                raise BoardPackValidationError(
                    f"agenda_item {agenda_item_id} does not belong to parent meeting"
                )

        # Get max position
        max_row = conn.execute(
            "SELECT COALESCE(MAX(position), 0) AS max_pos FROM board_pack_item WHERE board_pack_id = %s",
            (pack_uuid,),
        ).fetchone()
        max_pos = max_row["max_pos"] if max_row else 0

        if position is None or position > max_pos + 1:
            target_pos = max_pos + 1
        elif position <= 0:
            raise BoardPackValidationError("position must be positive")
        else:
            target_pos = position
            conn.execute(
                """
                UPDATE board_pack_item
                   SET position = position + 1
                 WHERE board_pack_id = %s AND position >= %s
                """,
                (pack_uuid, target_pos),
            )

        row = conn.execute(
            """
            INSERT INTO board_pack_item
                (board_pack_id, document_id, agenda_item_id, position, note, workspace_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                pack_uuid,
                doc_uuid,
                ag_uuid,
                target_pos,
                note.strip() if note and note.strip() else None,
                workspace_id,
            ),
        ).fetchone()

        # Touch pack updated_at and bump version
        conn.execute(
            "UPDATE board_pack SET version = version + 1, updated_at = now() WHERE id = %s",
            (pack_uuid,),
        )

    return _row_to_pack_item(row)


def remove_pack_item(
    pack_item_id: str,
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> None:
    """Removes an item from a draft board pack and shifts subsequent positions down by 1."""
    item_uuid = uuid.UUID(str(pack_item_id))

    with store.pg(workspace_id) as conn:
        item = conn.execute(
            "SELECT board_pack_id, position FROM board_pack_item WHERE id = %s FOR UPDATE",
            (item_uuid,),
        ).fetchone()
        if item is None:
            raise BoardPackValidationError(f"board_pack_item {pack_item_id} not found")

        pack_uuid = item["board_pack_id"]
        deleted_pos = item["position"]

        pack = conn.execute(
            "SELECT meeting_id, status FROM board_pack WHERE id = %s FOR UPDATE",
            (pack_uuid,),
        ).fetchone()
        if pack is None or pack["status"] != DRAFT:
            raise BoardPackLockedError("cannot remove items from non-draft board pack")

        _assert_meeting_pre_meeting(conn, pack["meeting_id"])

        conn.execute("DELETE FROM board_pack_item WHERE id = %s", (item_uuid,))
        conn.execute(
            """
            UPDATE board_pack_item
               SET position = position - 1
             WHERE board_pack_id = %s AND position > %s
            """,
            (pack_uuid, deleted_pos),
        )
        conn.execute(
            "UPDATE board_pack SET version = version + 1, updated_at = now() WHERE id = %s",
            (pack_uuid,),
        )


def publish_pack(
    pack_id: str,
    *,
    expected_version: int,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    clearance: int,
) -> BoardPack:
    """Publishes a draft board pack, locking its contents and setting published_at."""
    pack_uuid = uuid.UUID(str(pack_id))

    with store.pg(workspace_id) as conn:
        current = conn.execute(
            "SELECT meeting_id, status, version FROM board_pack WHERE id = %s FOR UPDATE",
            (pack_uuid,),
        ).fetchone()
        if current is None:
            raise BoardPackNotFound(str(pack_id))

        if current["version"] != expected_version:
            raise StaleBoardPackError(
                f"board_pack {pack_id}: expected version {expected_version}, current {current['version']}"
            )

        if current["status"] != DRAFT:
            raise BoardPackValidationError(f"cannot publish board pack in status {current['status']!r}")

        _assert_meeting_pre_meeting(conn, current["meeting_id"])

        row = conn.execute(
            """
            UPDATE board_pack
               SET status = 'published', published_at = now(), version = version + 1, updated_at = now()
             WHERE id = %s AND version = %s
            RETURNING *
            """,
            (pack_uuid, expected_version),
        ).fetchone()

        if row is None:
            raise StaleBoardPackError(f"board_pack {pack_id}: concurrent modification")

        items = _fetch_items_for_packs(conn, [pack_uuid], clearance=clearance).get(str(pack_uuid), [])

    return _row_to_board_pack(row, items=items)


def supersede_pack(
    old_pack_id: str,
    new_title: str,
    *,
    expected_version: int,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    clearance: int,
) -> tuple[BoardPack, BoardPack]:
    """Supersedes a published board pack with a new draft board pack version."""
    if not new_title or not new_title.strip():
        raise BoardPackValidationError("new_title must not be empty")

    old_uuid = uuid.UUID(str(old_pack_id))

    with store.pg(workspace_id) as conn:
        old_row = conn.execute(
            "SELECT meeting_id, status, version, version_no FROM board_pack WHERE id = %s FOR UPDATE",
            (old_uuid,),
        ).fetchone()
        if old_row is None:
            raise BoardPackNotFound(str(old_pack_id))

        if old_row["version"] != expected_version:
            raise StaleBoardPackError(
                f"board_pack {old_pack_id}: expected version {expected_version}, current {old_row['version']}"
            )

        if old_row["status"] != PUBLISHED:
            raise BoardPackValidationError(
                f"only PUBLISHED board packs can be superseded; current status is {old_row['status']!r}"
            )

        _assert_meeting_pre_meeting(conn, old_row["meeting_id"])

        # 1. Create new draft pack with version_no + 1
        new_row = conn.execute(
            """
            INSERT INTO board_pack
                (meeting_id, title, status, version_no, workspace_id)
            VALUES (%s, %s, 'draft', %s, %s)
            RETURNING *
            """,
            (
                old_row["meeting_id"],
                new_title.strip(),
                old_row["version_no"] + 1,
                workspace_id,
            ),
        ).fetchone()
        new_uuid = new_row["id"]

        # 2. Copy items from old pack to new pack (unfiltered copy preserves all pack items in DB)
        old_items = conn.execute(
            "SELECT * FROM board_pack_item WHERE board_pack_id = %s ORDER BY position ASC",
            (old_uuid,),
        ).fetchall()

        for it in old_items:
            conn.execute(
                """
                INSERT INTO board_pack_item
                    (board_pack_id, document_id, agenda_item_id, position, note, workspace_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    new_uuid,
                    it["document_id"],
                    it["agenda_item_id"],
                    it["position"],
                    it["note"],
                    workspace_id,
                ),
            )

        # 3. Update old pack to superseded_by_id = new_uuid
        updated_old = conn.execute(
            """
            UPDATE board_pack
               SET superseded_by_id = %s, version = version + 1, updated_at = now()
             WHERE id = %s AND version = %s
            RETURNING *
            """,
            (new_uuid, old_uuid, expected_version),
        ).fetchone()

        new_items = _fetch_items_for_packs(conn, [new_uuid], clearance=clearance).get(str(new_uuid), [])
        old_items_copied = _fetch_items_for_packs(conn, [old_uuid], clearance=clearance).get(str(old_uuid), [])

    return _row_to_board_pack(new_row, items=new_items), _row_to_board_pack(updated_old, items=old_items_copied)


def reorder_pack_items(
    pack_id: str,
    ordered_item_ids: list[str],
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    clearance: int,
) -> BoardPack:
    """Reorders the items of a draft board pack to match `ordered_item_ids` (1..N)."""
    if not ordered_item_ids:
        raise BoardPackValidationError("ordered_item_ids must not be empty")

    pack_uuid = uuid.UUID(str(pack_id))
    item_uuids = [uuid.UUID(str(i)) for i in ordered_item_ids]

    with store.pg(workspace_id) as conn:
        pack = conn.execute(
            "SELECT meeting_id, status, version FROM board_pack WHERE id = %s FOR UPDATE",
            (pack_uuid,),
        ).fetchone()
        if pack is None:
            raise BoardPackNotFound(str(pack_id))

        if pack["status"] != DRAFT:
            raise BoardPackLockedError(
                f"cannot reorder items for board pack in status {pack['status']!r}; published packs are immutable"
            )

        _assert_meeting_pre_meeting(conn, pack["meeting_id"])

        existing_items = conn.execute(
            "SELECT id FROM board_pack_item WHERE board_pack_id = %s", (pack_uuid,)
        ).fetchall()
        existing_ids = {r["id"] for r in existing_items}

        if set(item_uuids) != existing_ids or len(item_uuids) != len(existing_ids):
            raise BoardPackValidationError(
                "ordered_item_ids must contain exactly the existing item IDs for this board pack"
            )

        # Temporary positive offset assignment to avoid UNIQUE constraint collision during swap
        for idx, item_id in enumerate(item_uuids, start=1):
            conn.execute(
                "UPDATE board_pack_item SET position = %s WHERE id = %s AND board_pack_id = %s",
                (idx + 10000, item_id, pack_uuid),
            )

        for idx, item_id in enumerate(item_uuids, start=1):
            conn.execute(
                "UPDATE board_pack_item SET position = %s WHERE id = %s AND board_pack_id = %s",
                (idx, item_id, pack_uuid),
            )

        row = conn.execute(
            "UPDATE board_pack SET version = version + 1, updated_at = now() WHERE id = %s RETURNING *",
            (pack_uuid,),
        ).fetchone()

        items = _fetch_items_for_packs(conn, [pack_uuid], clearance=clearance).get(str(pack_uuid), [])

    return _row_to_board_pack(row, items=items)

