"""Commitment domain — product-domain aggregate (Meridian P2, checkpoint 7).

This module owns the accountable work a decision produced, and the append-only trail
of updates against it. FR-EXEC-01: owner, accountable team, due date, status, source
decision, evidence pointer.

Design contract:
  - All database operations execute through `store.pg(workspace_id)` under `callosum_app`
    role, so Row-Level Security automatically enforces tenant isolation.
  - A commitment CANNOT exist without a source decision. `decision_id` is NOT NULL and
    composite-FK'd; untraceable work is what this product exists to prevent.
  - Lifecycle: `open` -> `in_progress` | `blocked` | `cancelled`;
    `in_progress` -> `completed` | `blocked` | `cancelled`;
    `blocked` -> `in_progress` | `cancelled`. Only `completed` and `cancelled` are
    terminal — a blocked task is expected to unblock.
  - Updates are append-only. There is no edit or delete path, because an editable
    trail is not evidence.
  - Every mutation is version-guarded by optimistic concurrency (`version = version + 1`).

DELIBERATELY NOT LOCKED TO THE MEETING. Unlike resolutions, a commitment must remain
workable long after its meeting is completed — reporting progress at the *next* meeting
is the entire point of the object. There is no `_LOCKED_MEETING_STATUSES` here, and its
absence is a decision rather than an omission.

DELIVERY IS INERT IN P2. `external_system`, `external_task_id`, `delivery_status` and
`delivery_attempts` model retry STATE; no adapter dispatches anything. FR-EXEC-03 —
failed delivery must never falsely mark an action delivered — is enforced by a CHECK
constraint in `0015_commitment`, not by this module, so it holds against direct SQL too.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from callosum import store
from callosum.store import DEFAULT_WORKSPACE_ID

OPEN = "open"
IN_PROGRESS = "in_progress"
BLOCKED = "blocked"
COMPLETED = "completed"
CANCELLED = "cancelled"

COMMITMENT_STATUSES = frozenset({OPEN, IN_PROGRESS, BLOCKED, COMPLETED, CANCELLED})

_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    OPEN: frozenset({IN_PROGRESS, BLOCKED, CANCELLED}),
    IN_PROGRESS: frozenset({COMPLETED, BLOCKED, CANCELLED}),
    # Not terminal, on purpose. Work that is blocked is expected to resume; making
    # this an exit would repeat the `deferred` (CP4) and `archived` (CP6) mistake.
    BLOCKED: frozenset({IN_PROGRESS, CANCELLED}),
    COMPLETED: frozenset(),
    CANCELLED: frozenset(),
}

NOT_DISPATCHED = "not_dispatched"
PENDING = "pending"
DELIVERED = "delivered"
FAILED = "failed"

DELIVERY_STATUSES = frozenset({NOT_DISPATCHED, PENDING, DELIVERED, FAILED})

_UNSET = object()


# ---------------------------------------------------------------------------
# Typed Domain Exceptions
# ---------------------------------------------------------------------------

class CommitmentError(Exception):
    """Base class for commitment-domain errors."""


class CommitmentNotFound(CommitmentError):
    """No commitment with that ID is visible in this workspace."""


class CommitmentLockedError(CommitmentError):
    """The commitment is in a terminal state, or the transition is not allowed."""


class StaleCommitmentError(CommitmentError):
    """Optimistic-concurrency conflict: commitment was modified since it was read."""


class CommitmentValidationError(CommitmentError):
    """Requested change violates domain rules (e.g. empty title, invalid status)."""


class DecisionNotFound(CommitmentError):
    """No decision with that ID is visible in this workspace.

    Raised for both "no such decision" and "belongs to another workspace": the
    RLS-scoped read cannot distinguish them, and reporting the difference would
    confirm the existence of another tenant's row.
    """


class ResolutionNotFound(CommitmentError):
    """No resolution with that ID is visible in this workspace."""


class BoardMemberNotFound(CommitmentError):
    """No board member with that ID is visible here, or they are inactive."""


# ---------------------------------------------------------------------------
# Read Models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CommitmentUpdate:
    id: str
    commitment_id: str
    note: str
    new_status: str | None
    author_board_member_id: str | None
    created_at: datetime
    workspace_id: str


@dataclass(frozen=True)
class Commitment:
    id: str
    decision_id: str
    resolution_id: str | None
    owner_board_member_id: str
    accountable_team: str | None
    title: str
    detail: str | None
    due_date: date | None
    status: str
    completed_at: datetime | None
    external_system: str | None
    external_task_id: str | None
    delivery_status: str
    delivery_attempts: int
    version: int
    created_at: datetime
    updated_at: datetime
    workspace_id: str
    updates: list[CommitmentUpdate]

    @property
    def is_open(self) -> bool:
        """True while the commitment still represents outstanding work."""
        return self.status in (OPEN, IN_PROGRESS, BLOCKED)

    def is_overdue(self, *, today: date) -> bool:
        """True when the due date has passed and the work is not closed.

        Takes `today` rather than reading the clock: a value that changes under the
        caller makes a report irreproducible, and this is exactly the kind of number
        that ends up on a dashboard.
        """
        if self.due_date is None or not self.is_open:
            return False
        return self.due_date < today


def _row_to_update(row: dict) -> CommitmentUpdate:
    return CommitmentUpdate(
        id=str(row["id"]),
        commitment_id=str(row["commitment_id"]),
        note=row["note"],
        new_status=row["new_status"],
        author_board_member_id=(
            str(row["author_board_member_id"]) if row["author_board_member_id"] else None
        ),
        created_at=row["created_at"],
        workspace_id=str(row["workspace_id"]),
    )


def _row_to_commitment(row: dict, updates: list[CommitmentUpdate]) -> Commitment:
    return Commitment(
        id=str(row["id"]),
        decision_id=str(row["decision_id"]),
        resolution_id=str(row["resolution_id"]) if row["resolution_id"] else None,
        owner_board_member_id=str(row["owner_board_member_id"]),
        accountable_team=row["accountable_team"],
        title=row["title"],
        detail=row["detail"],
        due_date=row["due_date"],
        status=row["status"],
        completed_at=row["completed_at"],
        external_system=row["external_system"],
        external_task_id=row["external_task_id"],
        delivery_status=row["delivery_status"],
        delivery_attempts=row["delivery_attempts"],
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        workspace_id=str(row["workspace_id"]),
        updates=updates,
    )


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _assert_active_member(conn, member_uuid: uuid.UUID) -> None:
    """Inactive and absent are conflated: both mean 'not assignable here'."""
    row = conn.execute(
        "SELECT active FROM board_member WHERE id = %s", (member_uuid,)
    ).fetchone()
    if row is None or not row["active"]:
        raise BoardMemberNotFound(str(member_uuid))


def _fetch_updates(conn, commitment_uuids: list[uuid.UUID]) -> dict[str, list[CommitmentUpdate]]:
    if not commitment_uuids:
        return {}
    rows = conn.execute(
        """
        SELECT * FROM commitment_update
         WHERE commitment_id = ANY(%s)
         ORDER BY created_at ASC
        """,
        (commitment_uuids,),
    ).fetchall()
    out: dict[str, list[CommitmentUpdate]] = {}
    for r in rows:
        u = _row_to_update(r)
        out.setdefault(u.commitment_id, []).append(u)
    return out


# ---------------------------------------------------------------------------
# Public Operations
# ---------------------------------------------------------------------------

def create_commitment(
    decision_id: str,
    title: str,
    owner_board_member_id: str,
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    resolution_id: str | None = None,
    accountable_team: str | None = None,
    detail: str | None = None,
    due_date: date | None = None,
) -> Commitment:
    """Creates an `open` commitment against `decision_id`, owned by a board member."""
    if not title or not title.strip():
        raise CommitmentValidationError("title must not be empty")

    dec_uuid = uuid.UUID(str(decision_id))
    owner_uuid = uuid.UUID(str(owner_board_member_id))
    res_uuid = uuid.UUID(str(resolution_id)) if resolution_id else None

    with store.pg(workspace_id) as conn:
        # RLS-scoped existence checks. The composite FKs would also reject a
        # cross-workspace id, but as a ForeignKeyViolation — callers should not have
        # to catch psycopg exceptions to handle a missing parent.
        if conn.execute("SELECT id FROM decision WHERE id = %s", (dec_uuid,)).fetchone() is None:
            raise DecisionNotFound(str(decision_id))

        _assert_active_member(conn, owner_uuid)

        if res_uuid is not None:
            res = conn.execute(
                "SELECT decision_id FROM resolution WHERE id = %s", (res_uuid,)
            ).fetchone()
            if res is None:
                raise ResolutionNotFound(str(resolution_id))
            # A commitment's evidence pointer must lead back to its own source.
            # Nothing in the schema prevents citing an unrelated resolution, and a
            # wrong citation is worse than none: it looks like provenance.
            if str(res["decision_id"]) != str(dec_uuid):
                raise CommitmentValidationError(
                    f"resolution {resolution_id} does not belong to decision {decision_id}"
                )

        row = conn.execute(
            """
            INSERT INTO commitment
                (decision_id, resolution_id, owner_board_member_id, accountable_team,
                 title, detail, due_date, status, workspace_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'open', %s)
            RETURNING *
            """,
            (
                dec_uuid,
                res_uuid,
                owner_uuid,
                accountable_team.strip() if accountable_team and accountable_team.strip() else None,
                title.strip(),
                detail.strip() if detail and detail.strip() else None,
                due_date,
                workspace_id,
            ),
        ).fetchone()

    return _row_to_commitment(row, updates=[])


def get_commitment(
    commitment_id: str, *, workspace_id: str = DEFAULT_WORKSPACE_ID
) -> Commitment:
    """Fetches one commitment with its update trail."""
    c_uuid = uuid.UUID(str(commitment_id))
    with store.pg(workspace_id) as conn:
        row = conn.execute("SELECT * FROM commitment WHERE id = %s", (c_uuid,)).fetchone()
        if row is None:
            raise CommitmentNotFound(str(commitment_id))
        updates = _fetch_updates(conn, [c_uuid]).get(str(c_uuid), [])
    return _row_to_commitment(row, updates=updates)


def list_commitments(
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    decision_id: str | None = None,
    owner_board_member_id: str | None = None,
    status: str | None = None,
    open_only: bool = False,
) -> list[Commitment]:
    """Returns commitments, soonest due first, then newest.

    `open_only` selects outstanding work (`open`, `in_progress`, `blocked`) — the
    question a board actually asks, which no single status answers.
    """
    query = "SELECT * FROM commitment WHERE true"
    params: list = []

    if decision_id is not None:
        query += " AND decision_id = %s"
        params.append(uuid.UUID(str(decision_id)))

    if owner_board_member_id is not None:
        query += " AND owner_board_member_id = %s"
        params.append(uuid.UUID(str(owner_board_member_id)))

    if status is not None:
        if status not in COMMITMENT_STATUSES:
            raise CommitmentValidationError(f"unknown commitment status: {status!r}")
        query += " AND status = %s"
        params.append(status)

    if open_only:
        query += " AND status IN ('open', 'in_progress', 'blocked')"

    # NULLS LAST so undated work sorts after dated work rather than ahead of it —
    # a commitment with no deadline is not the most urgent thing on the list.
    query += " ORDER BY due_date ASC NULLS LAST, created_at DESC"

    with store.pg(workspace_id) as conn:
        rows = conn.execute(query, params).fetchall()
        updates = _fetch_updates(conn, [r["id"] for r in rows])

    return [_row_to_commitment(r, updates=updates.get(str(r["id"]), [])) for r in rows]


def update_commitment(
    commitment_id: str,
    *,
    expected_version: int,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    title=_UNSET,
    detail=_UNSET,
    due_date=_UNSET,
    accountable_team=_UNSET,
    owner_board_member_id=_UNSET,
) -> Commitment:
    """Edits an open commitment's details under optimistic concurrency.

    Terminal commitments are immutable: a completed or cancelled record is history,
    and rewriting its owner or deadline after the fact would falsify what was agreed.
    """
    fields = {
        "title": title,
        "detail": detail,
        "due_date": due_date,
        "accountable_team": accountable_team,
        "owner_board_member_id": owner_board_member_id,
    }
    if all(v is _UNSET for v in fields.values()):
        raise CommitmentValidationError("no fields to update")

    if title is not _UNSET and (not title or not title.strip()):
        raise CommitmentValidationError("title must not be empty")

    c_uuid = uuid.UUID(str(commitment_id))

    with store.pg(workspace_id) as conn:
        current = conn.execute(
            "SELECT status, version FROM commitment WHERE id = %s FOR UPDATE", (c_uuid,)
        ).fetchone()
        if current is None:
            raise CommitmentNotFound(str(commitment_id))

        if current["version"] != expected_version:
            raise StaleCommitmentError(
                f"commitment {commitment_id}: expected version {expected_version}, "
                f"current {current['version']}"
            )

        if not _ALLOWED_TRANSITIONS[current["status"]]:
            raise CommitmentLockedError(
                f"cannot edit a commitment in terminal status {current['status']!r}"
            )

        sets, params = [], []
        if title is not _UNSET:
            sets.append("title = %s")
            params.append(title.strip())
        if detail is not _UNSET:
            sets.append("detail = %s")
            params.append(detail.strip() if detail and detail.strip() else None)
        if due_date is not _UNSET:
            sets.append("due_date = %s")
            params.append(due_date)
        if accountable_team is not _UNSET:
            sets.append("accountable_team = %s")
            params.append(
                accountable_team.strip()
                if accountable_team and accountable_team.strip()
                else None
            )
        if owner_board_member_id is not _UNSET:
            owner_uuid = uuid.UUID(str(owner_board_member_id))
            _assert_active_member(conn, owner_uuid)
            sets.append("owner_board_member_id = %s")
            params.append(owner_uuid)

        params.extend([c_uuid, expected_version])
        row = conn.execute(
            f"""
            UPDATE commitment
               SET {', '.join(sets)}, version = version + 1, updated_at = now()
             WHERE id = %s AND version = %s
            RETURNING *
            """,
            params,
        ).fetchone()

        if row is None:
            raise StaleCommitmentError(f"commitment {commitment_id}: concurrent modification")

        updates = _fetch_updates(conn, [c_uuid]).get(str(c_uuid), [])

    return _row_to_commitment(row, updates=updates)


def record_update(
    commitment_id: str,
    note: str,
    *,
    expected_version: int,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    new_status: str | None = None,
    author_board_member_id: str | None = None,
) -> Commitment:
    """Appends a progress note, optionally moving the commitment to `new_status`.

    This is the only way the status changes. Progress and the reason for it are
    recorded together, so the trail can never contain a state change with no account
    of why it happened — which is the difference between a status field and a record.
    """
    if not note or not note.strip():
        raise CommitmentValidationError("note must not be empty")

    if new_status is not None and new_status not in COMMITMENT_STATUSES:
        raise CommitmentValidationError(f"unknown commitment status: {new_status!r}")

    c_uuid = uuid.UUID(str(commitment_id))
    author_uuid = uuid.UUID(str(author_board_member_id)) if author_board_member_id else None

    with store.pg(workspace_id) as conn:
        current = conn.execute(
            "SELECT status, version FROM commitment WHERE id = %s FOR UPDATE", (c_uuid,)
        ).fetchone()
        if current is None:
            raise CommitmentNotFound(str(commitment_id))

        if current["version"] != expected_version:
            raise StaleCommitmentError(
                f"commitment {commitment_id}: expected version {expected_version}, "
                f"current {current['version']}"
            )

        allowed = _ALLOWED_TRANSITIONS[current["status"]]
        if not allowed:
            raise CommitmentLockedError(
                f"cannot update a commitment in terminal status {current['status']!r}"
            )

        if new_status is not None and new_status not in allowed:
            raise CommitmentLockedError(
                f"cannot move a commitment from {current['status']!r} to {new_status!r}"
            )

        if author_uuid is not None:
            _assert_active_member(conn, author_uuid)

        conn.execute(
            """
            INSERT INTO commitment_update
                (commitment_id, note, new_status, author_board_member_id, workspace_id)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (c_uuid, note.strip(), new_status, author_uuid, workspace_id),
        )

        if new_status is not None:
            row = conn.execute(
                """
                UPDATE commitment
                   SET status = %s,
                       completed_at = CASE WHEN %s = 'completed' THEN now() ELSE completed_at END,
                       version = version + 1,
                       updated_at = now()
                 WHERE id = %s AND version = %s
                RETURNING *
                """,
                (new_status, new_status, c_uuid, expected_version),
            ).fetchone()
        else:
            row = conn.execute(
                """
                UPDATE commitment
                   SET version = version + 1, updated_at = now()
                 WHERE id = %s AND version = %s
                RETURNING *
                """,
                (c_uuid, expected_version),
            ).fetchone()

        if row is None:
            raise StaleCommitmentError(f"commitment {commitment_id}: concurrent modification")

        from meridian import audit
        audit.record_audit_event(
            conn,
            aggregate_type="commitment",
            aggregate_id=c_uuid,
            action="status_changed" if new_status is not None else "updated",
            payload={"new_status": new_status, "note": note.strip()},
            workspace_id=workspace_id,
        )

        updates = _fetch_updates(conn, [c_uuid]).get(str(c_uuid), [])

    return _row_to_commitment(row, updates=updates)


def record_delivery_attempt(
    commitment_id: str,
    delivery_status: str,
    *,
    expected_version: int,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    external_system: str | None = None,
    external_task_id: str | None = None,
) -> Commitment:
    """Records the outcome of an external dispatch. Retry STATE only — P2 dispatches nothing.

    `delivered` requires both an external system and task id. That is also a CHECK
    constraint in `0015_commitment`; it is validated here as well so callers get a
    domain error rather than an IntegrityError, but the constraint is what makes
    FR-EXEC-03 hold against writes that never reach this function.

    `delivery_attempts` increments on every call including success, because the count
    is "how many times we tried", not "how many times we failed".
    """
    if delivery_status not in DELIVERY_STATUSES:
        raise CommitmentValidationError(f"unknown delivery status: {delivery_status!r}")

    c_uuid = uuid.UUID(str(commitment_id))

    with store.pg(workspace_id) as conn:
        current = conn.execute(
            """
            SELECT version, external_system, external_task_id
              FROM commitment WHERE id = %s FOR UPDATE
            """,
            (c_uuid,),
        ).fetchone()
        if current is None:
            raise CommitmentNotFound(str(commitment_id))

        if current["version"] != expected_version:
            raise StaleCommitmentError(
                f"commitment {commitment_id}: expected version {expected_version}, "
                f"current {current['version']}"
            )

        system = external_system if external_system is not None else current["external_system"]
        task_id = external_task_id if external_task_id is not None else current["external_task_id"]

        if delivery_status == DELIVERED and (not task_id or not system):
            raise CommitmentValidationError(
                "cannot mark delivery as 'delivered' without an external_system and "
                "external_task_id; a delivery that cannot be reconciled is not a delivery"
            )

        row = conn.execute(
            """
            UPDATE commitment
               SET delivery_status = %s,
                   external_system = %s,
                   external_task_id = %s,
                   delivery_attempts = delivery_attempts + 1,
                   version = version + 1,
                   updated_at = now()
             WHERE id = %s AND version = %s
            RETURNING *
            """,
            (delivery_status, system, task_id, c_uuid, expected_version),
        ).fetchone()

        if row is None:
            raise StaleCommitmentError(f"commitment {commitment_id}: concurrent modification")

        updates = _fetch_updates(conn, [c_uuid]).get(str(c_uuid), [])

    return _row_to_commitment(row, updates=updates)
