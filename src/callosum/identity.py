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


# The membership rule, written once.
#
# "A principal is resolvable here only if they hold an ACTIVE membership in THIS
# workspace, and their clearance is the membership's" — that sentence is the whole
# of P1's tenancy model, and it should exist in exactly one place. Every lookup in
# this module formats its own match predicate into this and changes nothing else.
#
# The JOIN is what enforces it. A post-filter would leave a code path on which a
# principal row is returned without a membership beside it; there is no such path
# here, and adding one would be the regression to watch for.
_PRINCIPAL_WITH_ACTIVE_MEMBERSHIP = """
    SELECT p.id, p.name, p.role, m.clearance
      FROM principal p
      JOIN membership m ON m.principal_id = p.id
     WHERE {match}
       AND m.workspace_id = %s
       AND m.active
    {order}
     LIMIT 1
"""


def _fetch_principal(
    conn: psycopg.Connection,
    *,
    match: str,
    match_param: object,
    workspace_id: str,
    order: str = "",
) -> dict | None:
    """Runs the membership-scoped lookup for a caller-supplied match predicate.

    `match` and `order` are module-level SQL fragments, never caller input — the only
    values that cross the boundary are bound parameters.
    """
    sql = _PRINCIPAL_WITH_ACTIVE_MEMBERSHIP.format(match=match, order=order)
    return conn.execute(sql, (match_param, workspace_id)).fetchone()


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
    row = _fetch_principal(
        conn,
        match="p.name ILIKE %s",
        match_param=f"%{name_fragment}%",
        workspace_id=workspace_id,
        order="ORDER BY p.name",
    )

    if row is None:
        raise PrincipalNotFound(name_fragment)

    return Principal(
        id=row["id"],
        name=row["name"],
        role=row["role"],
        clearance=row["clearance"],
        workspace_id=workspace_id,
    )


def resolve_principal_by_id(
    conn: psycopg.Connection,
    principal_id: uuid.UUID | str,
    *,
    workspace_id: str,
) -> Principal:
    """Resolves a caller by their stable `principal.id`, with clearance from membership.

    **This is the lookup an authenticated request should use.** `resolve_principal()`
    matches on `name ILIKE '%fragment%'` and returns the first alphabetical hit — a
    fine affordance for a CLI where a human types their own name, and an unacceptable
    authentication path, because two principals whose names share a substring resolve
    to whichever sorts first. An identifier that is stable, opaque and exact is the
    only sound basis for deciding who someone is.

    Fail-closed on exactly the same terms as `resolve_principal()`, because it is the
    same JOIN: a principal with no active membership in `workspace_id` does not
    resolve at all. `PrincipalNotFound` is raised for "no such id", "not a member
    here" and "membership deactivated" alike — telling them apart would confirm that
    an id is real to a caller who cannot read the directory.

    `workspace_id` is required rather than defaulted. Every other lookup in this
    module defaults to the Default Workspace for the frozen single-tenant CLI path;
    an authenticated request always knows its workspace, and defaulting one would
    reintroduce the fail-open behaviour `meridian.tenancy` exists to prevent.

    Validating that `workspace_id` is well-formed is the *caller's* job —
    `meridian.tenancy.require_workspace()` does it at the API boundary. This module
    cannot call that helper: Meridian imports Callosum, never the reverse, and
    inverting it would break the package separation R13 established.

    **What this deliberately does not do:** map an OIDC subject to a principal. That
    mapping is decision D2 in the P3 roadmap and needs a schema of its own; this
    function takes the principal id that mapping will eventually produce.
    """
    try:
        pid = principal_id if isinstance(principal_id, uuid.UUID) else uuid.UUID(str(principal_id))
    except (ValueError, TypeError, AttributeError) as exc:
        # A malformed id is not a lookup failure, but it must not leak a different
        # error shape either — a caller learning "that was invalid" versus "that was
        # not found" learns nothing useful, and the uniform answer is cheaper to reason
        # about than two.
        raise PrincipalNotFound(str(principal_id)) from exc

    row = _fetch_principal(
        conn,
        match="p.id = %s",
        match_param=pid,
        workspace_id=workspace_id,
    )

    if row is None:
        raise PrincipalNotFound(str(principal_id))

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
    row = _fetch_principal(
        conn,
        match="p.name ILIKE %s",
        match_param=f"%{name_fragment}%",
        workspace_id=workspace_id,
    )
    return row["id"] if row else None
