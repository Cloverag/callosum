"""BoardMember domain — governance directory (Meridian P2, checkpoint 5a).

This module owns the people who participate in a board: who they are, what
capacity they sit in, and whether they carry a vote.

**`board_member` is not `membership`, and the distinction is load-bearing.**

    membership      Can this login see this workspace, and at what clearance?
                    Keyed (principal_id, workspace_id). Requires a `principal`.

    board_member    Who sits on this board, in what capacity, with what vote?
                    Keyed on its own id. `principal_id` is NULLABLE.

A non-executive director who never signs in must still be recordable, votable
and assignable, which is why the link to `principal` is optional. Someone will
otherwise join these two tables wrongly; they overlap in subject and not in
meaning.

Design contract:
  - All database operations execute through `store.pg(workspace_id)` under the
    `callosum_app` role, so Row-Level Security enforces tenant isolation.
  - Roles: ('director', 'observer', 'executive', 'administrator', 'adviser').
  - Voting status: ('voting', 'non_voting', 'recused') — the member's STANDING
    status. Per-motion recusal belongs on the vote, not on the person.
  - Members are deactivated, never deleted: a member who recorded a stance must
    stay resolvable forever.
  - Every mutation is version-guarded by optimistic concurrency.
  - No clearance column. Clearance is `membership`'s, by the P1 design.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from callosum import store
from callosum.store import DEFAULT_WORKSPACE_ID

DIRECTOR = "director"
OBSERVER = "observer"
EXECUTIVE = "executive"
ADMINISTRATOR = "administrator"
ADVISER = "adviser"

ALLOWED_ROLES = frozenset({DIRECTOR, OBSERVER, EXECUTIVE, ADMINISTRATOR, ADVISER})

VOTING = "voting"
NON_VOTING = "non_voting"
RECUSED = "recused"

ALLOWED_VOTING = frozenset({VOTING, NON_VOTING, RECUSED})

# Sentinel so `update_member(..., organization=None)` can clear a field, which is
# distinguishable from omitting the argument. Same idiom as `decisions.py`.
_UNSET = object()


# ---------------------------------------------------------------------------
# Typed Domain Exceptions
# ---------------------------------------------------------------------------

class BoardMemberError(Exception):
    """Base class for board-member domain errors."""


class BoardMemberNotFound(BoardMemberError):
    """No board member with that ID is visible in this workspace."""


class StaleBoardMemberError(BoardMemberError):
    """Optimistic-concurrency conflict: the member was modified since it was read."""


class BoardMemberValidationError(BoardMemberError):
    """Requested change violates domain rules (empty name, unknown role or vote status)."""


# ---------------------------------------------------------------------------
# Read Model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BoardMember:
    id: str
    workspace_id: str
    #: NULL when this person has no login. Not a defect — see the module docstring.
    principal_id: str | None
    full_name: str
    organization: str | None
    role: str
    contact_email: str | None
    voting: str
    active: bool
    version: int
    created_at: datetime
    updated_at: datetime


def _row_to_member(row: dict) -> BoardMember:
    return BoardMember(
        id=str(row["id"]),
        workspace_id=str(row["workspace_id"]),
        principal_id=str(row["principal_id"]) if row["principal_id"] else None,
        full_name=row["full_name"],
        organization=row["organization"],
        role=row["role"],
        contact_email=row["contact_email"],
        voting=row["voting"],
        active=row["active"],
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _validate(full_name: str | None, role: str | None, voting: str | None) -> None:
    if full_name is not None and not full_name.strip():
        raise BoardMemberValidationError("full_name must not be empty")
    if role is not None and role not in ALLOWED_ROLES:
        raise BoardMemberValidationError(f"unknown board role: {role!r}")
    if voting is not None and voting not in ALLOWED_VOTING:
        raise BoardMemberValidationError(f"unknown voting status: {voting!r}")


# ---------------------------------------------------------------------------
# Public Operations
# ---------------------------------------------------------------------------

def create_member(
    full_name: str,
    role: str,
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    principal_id: str | None = None,
    organization: str | None = None,
    contact_email: str | None = None,
    voting: str = VOTING,
) -> BoardMember:
    """Adds a person to the board directory.

    `principal_id` is optional by design: a director with no login is still a
    board member.
    """
    _validate(full_name, role, voting)

    with store.pg(workspace_id) as conn:
        p_uuid = uuid.UUID(str(principal_id)) if principal_id else None
        if p_uuid:
            mem = conn.execute(
                "SELECT 1 FROM membership WHERE principal_id = %s AND workspace_id = %s",
                (p_uuid, workspace_id),
            ).fetchone()
            if not mem:
                raise BoardMemberValidationError(
                    f"Principal {principal_id} does not have membership in workspace {workspace_id}"
                )

        row = conn.execute(
            """
            INSERT INTO board_member
                (workspace_id, principal_id, full_name, organization, role, contact_email, voting)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                workspace_id,
                p_uuid,
                full_name.strip(),
                organization.strip() if organization and organization.strip() else None,
                role,
                contact_email.strip() if contact_email and contact_email.strip() else None,
                voting,
            ),
        ).fetchone()

    return _row_to_member(row)


def get_member(member_id: str, *, workspace_id: str = DEFAULT_WORKSPACE_ID) -> BoardMember:
    """Fetches one member by id, active or not.

    Deliberately returns inactive members: historical stances resolve through
    this, and a departed director must not become unresolvable.
    """
    member_uuid = uuid.UUID(str(member_id))
    with store.pg(workspace_id) as conn:
        row = conn.execute(
            "SELECT * FROM board_member WHERE id = %s", (member_uuid,)
        ).fetchone()
    if row is None:
        raise BoardMemberNotFound(str(member_id))
    return _row_to_member(row)


def list_members(
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    active: bool | None = True,
    role: str | None = None,
) -> list[BoardMember]:
    """Lists the directory, active members only unless asked otherwise.

    `active=True` is the default because the directory's everyday use is "who is
    on the board now". Pass `active=None` for the full historical roster.
    """
    if role is not None and role not in ALLOWED_ROLES:
        raise BoardMemberValidationError(f"unknown board role: {role!r}")

    query = "SELECT * FROM board_member WHERE TRUE"
    params: list = []

    if active is not None:
        query += " AND active = %s"
        params.append(active)
    if role is not None:
        query += " AND role = %s"
        params.append(role)

    query += " ORDER BY full_name ASC, created_at ASC"

    with store.pg(workspace_id) as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_member(r) for r in rows]


def update_member(
    member_id: str,
    *,
    expected_version: int,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    full_name=_UNSET,
    organization=_UNSET,
    role=_UNSET,
    contact_email=_UNSET,
    voting=_UNSET,
) -> BoardMember:
    """Updates directory fields under optimistic concurrency.

    `active` is not settable here — use `deactivate_member` / `reactivate_member`,
    so a departure is an explicit act rather than a field edit.
    """
    _validate(
        full_name if full_name is not _UNSET else None,
        role if role is not _UNSET else None,
        voting if voting is not _UNSET else None,
    )

    sets: list[str] = []
    params: list = []

    if full_name is not _UNSET:
        sets.append("full_name = %s")
        params.append(full_name.strip())
    if organization is not _UNSET:
        sets.append("organization = %s")
        params.append(organization.strip() if organization and organization.strip() else None)
    if role is not _UNSET:
        sets.append("role = %s")
        params.append(role)
    if contact_email is not _UNSET:
        sets.append("contact_email = %s")
        params.append(contact_email.strip() if contact_email and contact_email.strip() else None)
    if voting is not _UNSET:
        sets.append("voting = %s")
        params.append(voting)

    if not sets:
        raise BoardMemberValidationError("no fields to update")

    return _apply_update(member_id, sets, params, expected_version, workspace_id)


def deactivate_member(
    member_id: str, *, expected_version: int, workspace_id: str = DEFAULT_WORKSPACE_ID
) -> BoardMember:
    """Marks a member inactive. There is no hard delete, deliberately.

    A member who recorded a stance or cast a vote must remain resolvable forever:
    deleting them would orphan history the immutability contract says is
    permanent. Inactive members drop out of the default `list_members()` but
    still resolve by id.
    """
    return _apply_update(member_id, ["active = false"], [], expected_version, workspace_id)


def reactivate_member(
    member_id: str, *, expected_version: int, workspace_id: str = DEFAULT_WORKSPACE_ID
) -> BoardMember:
    """Returns a previously departed member to the active roster."""
    return _apply_update(member_id, ["active = true"], [], expected_version, workspace_id)


def _apply_update(
    member_id: str,
    sets: list[str],
    params: list,
    expected_version: int,
    workspace_id: str,
) -> BoardMember:
    """Shared version-guarded write.

    The guard is `WHERE id = %s AND version = %s`: zero rows updated means either
    the member is invisible in this workspace or someone else wrote first, and
    those are distinguished by a follow-up read rather than by guessing.
    """
    member_uuid = uuid.UUID(str(member_id))
    sets = [*sets, "version = version + 1", "updated_at = now()"]

    with store.pg(workspace_id) as conn:
        row = conn.execute(
            f"UPDATE board_member SET {', '.join(sets)} "
            "WHERE id = %s AND version = %s RETURNING *",
            (*params, member_uuid, expected_version),
        ).fetchone()

        if row is None:
            exists = conn.execute(
                "SELECT 1 FROM board_member WHERE id = %s", (member_uuid,)
            ).fetchone()
            if exists is None:
                raise BoardMemberNotFound(str(member_id))
            raise StaleBoardMemberError(
                f"board member {member_id} was modified since version {expected_version}"
            )

    return _row_to_member(row)
