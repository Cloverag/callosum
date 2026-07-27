"""Resolve who is asking, and at what clearance (Meridian P2, checkpoint 5b).

P1 moved clearance from a global `principal.clearance` column to a per-workspace
`membership` row. The *runtime never adopted it*: every caller-lookup in `cli.py`
read `principal.clearance` directly, and `membership` sat empty with no readers.
This module is where that gets corrected.

**Clearance is a property of a membership, not of a person.** The same individual
may be a founder with full clearance in one workspace and hold no membership at
all in another; a global column cannot express that, and reading one silently
grants cross-tenant access at whatever level the person holds anywhere.

This module is deliberately NOT part of the frozen core. `retrieve.py` is frozen
and stays untouched: it receives a `Principal` and gates on `.clearance` exactly
as before. Only the *construction* of that object moves here.
"""

import uuid

import psycopg

from callosum.retrieve import Principal
from callosum.store import DEFAULT_WORKSPACE_ID


class PrincipalNotFound(Exception):
    """No principal matches, or they hold no active membership in this workspace.

    Both cases are one error on purpose. Distinguishing "no such person" from
    "that person exists but not here" tells an unauthorized caller whether a name
    is real, which is a membership oracle. The caller gets one answer: not
    available to you.
    """


def resolve_principal(
    conn: psycopg.Connection,
    name_fragment: str,
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> Principal:
    """Resolves a caller by name fragment, with clearance from their membership.

    **Fail-closed.** A principal with no active membership in `workspace_id` does
    not resolve at all — they are not granted their old global clearance, and not
    granted clearance 0 either. No membership means no access, which is the whole
    point of moving clearance onto the membership.

    The join does the enforcing rather than a post-filter, so there is no code
    path on which a principal row is returned without a membership beside it.
    """
    row = conn.execute(
        """
        SELECT p.id, p.name, p.role, m.clearance
          FROM principal p
          JOIN membership m ON m.principal_id = p.id
         WHERE p.name ILIKE %s
           AND m.workspace_id = %s
           AND m.active
         ORDER BY p.name
         LIMIT 1
        """,
        (f"%{name_fragment}%", workspace_id),
    ).fetchone()

    if row is None:
        raise PrincipalNotFound(name_fragment)

    return Principal(
        id=row["id"],
        name=row["name"],
        role=row["role"],
        clearance=row["clearance"],
        workspace_id=workspace_id,
    )


def resolve_principal_id(
    conn: psycopg.Connection,
    name_fragment: str,
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> uuid.UUID | None:
    """Resolves a caller to an id only, for attribution rather than authorization.

    Used where a reviewer is being *recorded* rather than *authorized* — the id is
    stamped on an approval, and no clearance decision hangs off it. Still scoped
    through membership, so a name from another workspace does not become a valid
    reviewer here.
    """
    row = conn.execute(
        """
        SELECT p.id
          FROM principal p
          JOIN membership m ON m.principal_id = p.id
         WHERE p.name ILIKE %s
           AND m.workspace_id = %s
           AND m.active
         LIMIT 1
        """,
        (f"%{name_fragment}%", workspace_id),
    ).fetchone()
    return row["id"] if row else None
