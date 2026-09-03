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

--------------------------------------------------------------------------------
ROLE IS NOW AUTHORITATIVE; STORED `membership.clearance` IS NOT (#166, P4)
--------------------------------------------------------------------------------
Superseding the checkpoint-5b design above without erasing it: that design made
`membership.clearance` the read authority, which was correct relative to the
column it replaced (`principal.clearance`, global, wrong for a tenancy model) but
is itself now superseded. `membership.role` is authoritative; clearance is
*derived* from it via `ROLE_TO_CLEARANCE`, and the stored `membership.clearance`
column is no longer read for authorization at all.

The reason is drift: `membership.clearance` and `membership.role` are two columns
with nothing forcing them to agree (`docs/reviews/2026-09-03-p4-membership-
decision-brief.md` §12.3, an artefact `cli.py:123`'s single-INSERT seeding made
look like agreement until it was checked). A role change that left the stored
clearance stale would make the anti-escalation check compare against an obsolete
privilege level — reading the mapping, not the column, is what makes that
impossible rather than merely unlikely.

`ROLE_TO_CLEARANCE` lives here and not in `meridian/` even though it exists for
`membership.role` — a `meridian`-owned table — because this module is on the
*frozen* CLI/eval path too (`cli.py` calls `resolve_principal`/
`resolve_principal_id` directly), and Meridian imports Callosum, never the
reverse. A mapping importable only from `meridian` would leave that path unable
to derive clearance from role, forcing it back onto the stored column and
reopening exactly the drift this change exists to close.
"""

import uuid

import psycopg

from callosum.retrieve import Principal
from callosum.store import DEFAULT_WORKSPACE_ID

#: The canonical seven, and the clearance each maps to. Mirrors the vocabulary
#: `0027_membership_role_and_audit`'s `membership_role_check` constrains at the
#: database layer (a separate, not-yet-merged branch) — defined independently
#: here rather than imported, because this module cannot assume that branch has
#: landed, and a Python dict has no migration dependency to declare.
#:
#: Maintainer-approved values (decision brief §11, Q2/Q3): `admin` carries
#: clearance 4 *and* separately carries membership-management authority — the
#: two are distinct grants on one role, and this mapping is only the first of
#: them. The second (who may grant which role to whom) is `#166` step 5, not here.
ROLE_TO_CLEARANCE: dict[str, int] = {
    "founder": 4,
    "admin": 4,
    "exec": 3,
    "director": 3,
    "advisor": 2,
    "investor": 1,
    "observer": 0,
}


class PrincipalNotFound(Exception):
    """No principal matches, or they hold no active membership in this workspace.

    Both cases are one error on purpose. Distinguishing "no such person" from
    "that person exists but not here" tells an unauthorized caller whether a name
    is real, which is a membership oracle. The caller gets one answer: not
    available to you.
    """


class IdentityNotProvisioned(PrincipalNotFound):
    """The external identity authenticated, but no `principal_identity` row maps it.

    ADR-011: an unknown subject is rejected rather than auto-provisioned, so this is
    the expected outcome for a stranger the identity provider is willing to
    authenticate — not an error condition to work around.

    **Distinct from `PrincipalNotFound`, and safe to be distinct**, because there is
    no membership oracle here: reaching this point required proving control of the
    subject through OIDC, so the caller only learns a fact about their *own* account.
    That distinction is what lets a login page say "ask an administrator for access"
    instead of a bare refusal.

    It subclasses `PrincipalNotFound` so every existing `except PrincipalNotFound`
    still catches it — a caller that does not care about the difference cannot
    accidentally let this one through.
    """


# The membership rule, written once.
#
# "A principal is resolvable here only if they hold an ACTIVE membership in THIS
# workspace, and their role is the membership's" — that sentence is the whole
# of P1's tenancy model, and it should exist in exactly one place. Every lookup in
# this module formats its own match predicate into this and changes nothing else.
#
# The JOIN is what enforces it. A post-filter would leave a code path on which a
# principal row is returned without a membership beside it; there is no such path
# here, and adding one would be the regression to watch for.
#
# `m.role`, not `p.role`: role is per-workspace now (#166), the same way clearance
# became per-workspace at checkpoint 5b — a founder in their own workspace may hold
# a lesser role, and therefore lesser clearance, in another. `m.clearance` is
# deliberately NOT selected: it is written (`cli.py:125`) but no longer read for
# authorization anywhere, and selecting a column this module does not use would
# invite a future edit to reach for it out of habit.
_PRINCIPAL_WITH_ACTIVE_MEMBERSHIP = """
    SELECT p.id, p.name, m.role
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


def _clearance_for(role: str) -> int:
    """Maps a `membership.role` to its clearance. Fails closed on an unrecognised one.

    Reachable today only if a role enters `membership` that `0027`'s CHECK would
    refuse — this branch does not carry that migration, and `ROLE_TO_CLEARANCE`
    could in principle drift from a CHECK that does land, in either direction. An
    unrecognised role is treated as unresolvable rather than given clearance 0 or
    raising a bare `KeyError`: this module's existing idiom is one failure shape,
    not a partial grant and not a crash a caller has to know to catch.
    """
    try:
        return ROLE_TO_CLEARANCE[role]
    except KeyError:
        raise PrincipalNotFound(role) from None


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
        clearance=_clearance_for(row["role"]),
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
    is `resolve_identity()`, which reads `principal_identity` and takes no workspace,
    because login happens before one is chosen. This function takes the principal id
    that lookup produces. `resolve_principal_by_subject()` composes the two.
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
        clearance=_clearance_for(row["role"]),
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


def resolve_identity(
    conn: psycopg.Connection,
    provider: str,
    subject: str,
) -> uuid.UUID:
    """Maps an authenticated OIDC `(issuer, subject)` onto a `principal.id`.

    **Deliberately takes no workspace.** This runs at login, before a workspace has
    been selected — there is nothing to scope by yet, and `principal_identity` is not
    tenant-scoped for exactly that reason (ADR-010). Clearance is *not* resolved here;
    it is a property of a membership, and which membership depends on the workspace
    the caller goes on to choose.

    So this is only half of authentication. The other half is
    `resolve_principal_by_id()`, which applies the membership rule once a workspace is
    known. Splitting them is what keeps identity global and authorization per-tenant.

    Raises `IdentityNotProvisioned` when no row maps the subject. Provisioning is an
    administrative act (ADR-011) and this function never creates one — the runtime
    role does not even hold `INSERT` on the table.

    Matching is exact and case-sensitive on both columns. Subjects are opaque, and
    issuers are compared verbatim by the OIDC spec; normalising either would risk
    collapsing two distinct identities into one.
    """
    if not provider or not provider.strip():
        raise IdentityNotProvisioned("provider must not be empty")
    if not subject or not subject.strip():
        raise IdentityNotProvisioned("subject must not be empty")

    row = conn.execute(
        """
        SELECT principal_id
          FROM principal_identity
         WHERE provider = %s
           AND subject = %s
        """,
        (provider, subject),
    ).fetchone()

    if row is None:
        # The subject is not echoed back. It is the caller's own, so this is not a
        # leak — but an exception message ends up in logs, and an external identifier
        # is not something to scatter through them by default.
        raise IdentityNotProvisioned("no principal is provisioned for that identity")

    return row["principal_id"]


def resolve_principal_by_subject(
    conn: psycopg.Connection,
    provider: str,
    subject: str,
    *,
    workspace_id: str,
) -> Principal:
    """Both halves: external identity → principal → clearance in this workspace.

    The composition an authenticated request uses once its workspace is settled.
    Equivalent to `resolve_principal_by_id(conn, resolve_identity(...), ...)`, and
    written as a composition rather than a second query so the membership rule stays
    in one place.

    Raises `IdentityNotProvisioned` if the subject maps to nobody, and
    `PrincipalNotFound` if it maps to someone with no active membership in
    `workspace_id`. Both are refusals; the first is about the account, the second
    about this tenant.

    `workspace_id` is required and unvalidated here by design — validating it belongs
    to `meridian.tenancy.require_workspace()` at the API boundary, and this module
    cannot import that helper without inverting the Meridian → Callosum dependency.
    """
    principal_id = resolve_identity(conn, provider, subject)
    return resolve_principal_by_id(conn, principal_id, workspace_id=workspace_id)
