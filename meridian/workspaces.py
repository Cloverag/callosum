"""Workspace bootstrap and membership administration (#166 step 5).

Two distinct operations, deliberately not one generalised grant path (issue #166
comment 5530505507, the maintainer's ruling):

    Bootstrap    Creates a workspace AND its founder membership together, through
                 `create_workspace_with_founder()` (migration 0029) — a
                 SECURITY DEFINER function that takes no workspace id, no role and
                 no clearance. `callosum_app` holds EXECUTE on it, never INSERT on
                 `workspace` itself.

    Grant/change/revoke
                 Ordinary INSERT/UPDATE on `membership` for a workspace the caller
                 is ALREADY a member of. `callosum_app` holds these grants directly
                 (narrowed from 0011 by the same migration).

CROSS-WORKSPACE REFUSAL IS AN AUTHORIZATION CHECK, NOT AN RLS SIDE EFFECT
--------------------------------------------------------------------------------
An earlier version of this docstring claimed "there is no code path in this module
that could produce a cross-workspace write ... because the SQL cannot express one."
That was false, and a test written to prove it (`test_a_cross_workspace_grant_is_
denied`) proved the opposite instead: `membership`'s WITH CHECK (`workspace_id =
current_setting('app.workspace_id')`) only catches a MISMATCH between the target
row's `workspace_id` and the connection's own RLS scope — and `store.pg(workspace_id)`
scopes the connection to the SAME `workspace_id` the write targets, by construction.
There is no mismatch for WITH CHECK to catch; the raw INSERT succeeds regardless of
who the actor is.

So the actual guard is `identity.resolve_principal_by_id()`, called first, on the
same connection: it raises `PrincipalNotFound` for an actor with no ACTIVE
membership in `workspace_id`, before any write is attempted. That is the real
cross-workspace refusal, and it does not depend on the audit write happening,
succeeding, or running before the mutation — unlike an earlier version of this
module, which took the actor's clearance as a caller-supplied argument and only
discovered a cross-workspace actor when `record_audit_event()`'s own membership
check rejected the audit row after the mutation had already been written (rolled
back by the transaction, but as a side effect of logging, not as an authorization
decision). The maintainer's ruling on this exact point: "Client-supplied
role/clearance values are untrusted." Resolving the actor from the database, on
the connection already scoped to the target workspace, is what makes that hold.

Anti-escalation is the one rule both a grant and a revoke enforce, symmetrically:
a caller may never act at a clearance ABOVE their own. Granting a role whose
`ROLE_TO_CLEARANCE` exceeds the actor's own clearance is refused outright — this
half is the maintainer's explicit ruling. Revoking a member whose current clearance
exceeds the actor's is refused for the same reason, though the ruling only stated
the grant half: an actor who could not have granted that role should not be able to
strip it either, or revoke-then-regrant becomes an escalation path the grant-side
check does not close. **Flagged here as my own extension of the rule, raised with
the maintainer for a ruling and not yet one — do not read this paragraph as policy
until that lands.**

Both checks compare against a role-derived clearance, on BOTH sides, never against
`membership.clearance` directly. That column is written on every mutation here
(mirroring `cli.py:125`'s existing convention) but it is legacy and can disagree
with `role` — `cli.py:125` seeds it from `principal.clearance`, independently of
`principal.role`, and #182 documents fifteen fixtures where the two already
disagree. Reading the stored column for an authorization decision — which
`revoke_membership` did, in an earlier version of this function — is exactly the
drift #166 step 3 closed for reads, reopened here for a write. Caught before this
module's first PR, not found by CI: see `revoke_membership`'s docstring for the
test that could not have caught it and the one substituted instead.
"""

from dataclasses import dataclass

from callosum import identity, store
from callosum.store import DEFAULT_WORKSPACE_ID

from meridian import audit


class WorkspaceError(Exception):
    """Base class for this module's domain errors."""


class UnknownRoleError(WorkspaceError):
    """The requested role is not one `ROLE_TO_CLEARANCE` recognises.

    The `membership_role_check` CHECK constraint (0027) would refuse the write in
    any case; this is raised earlier, before a query is even built, so the error a
    caller sees names the actual problem instead of a bare `CheckViolation`.
    """


class EscalationDeniedError(WorkspaceError):
    """The actor's own clearance does not cover the role or membership being acted on.

    Deliberately does not say what the actor's clearance IS, or what the target's
    was — only that the action is refused. Saying more would let repeated grant
    attempts probe another principal's exact clearance level, which is the same
    oracle `identity.PrincipalNotFound` and `audit.ActorNotInWorkspace` are written
    to avoid elsewhere in this codebase.
    """


class MembershipNotFoundError(WorkspaceError):
    """No membership row for that principal in this workspace."""


@dataclass(frozen=True)
class Membership:
    """A read model for one `membership` row.

    No `version` field, unlike this codebase's other read models: `membership` has
    no `version` column — its primary key is `(principal_id, workspace_id)`, and
    grant/revoke here are upsert/status-flip rather than optimistic-concurrency
    updates. There is nothing to guard: a grant that races another grant simply
    produces whichever role committed last, which is the same "last write wins"
    behaviour a direct superuser edit would have had before this route existed.
    """

    principal_id: str
    workspace_id: str
    role: str
    clearance: int
    active: bool


def _row_to_membership(row: dict) -> Membership:
    return Membership(
        principal_id=str(row["principal_id"]),
        workspace_id=str(row["workspace_id"]),
        role=row["role"],
        clearance=row["clearance"],
        active=row["active"],
    )


def _clearance_for(role: str) -> int:
    try:
        return identity.ROLE_TO_CLEARANCE[role]
    except KeyError:
        raise UnknownRoleError(role) from None


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def create_workspace(name: str, external_id: str | None, creator_principal_id: str) -> str:
    """Creates a workspace with `creator_principal_id` as its founder. Returns the new id.

    The one caller of `create_workspace_with_founder()` (migration 0029). That
    function does not take a workspace id — nothing here does either, and nothing
    should: the id this returns is the only place it is decided, generated inside
    the SECURITY DEFINER function itself.

    The audit write happens in the SAME transaction as the SQL call, after it
    returns. It cannot happen before: `record_audit_event()` requires the actor to
    hold an ACTIVE membership in the target workspace (`ActorNotInWorkspace`), and
    before this call returns, neither the workspace nor that membership exist yet.
    The session's RLS scope is retargeted to the new workspace mid-transaction
    (`set_config(..., is_local=false)` takes effect immediately, not only after
    commit) so the audit insert satisfies `audit_event`'s own WITH CHECK — opening
    a second connection instead would split the creation and its audit record
    across two transactions, and a crash between them would leave a founder
    membership with no audit trail naming how it got there.
    """
    if not name or not name.strip():
        raise WorkspaceError("name must not be empty")

    with store.pg(DEFAULT_WORKSPACE_ID) as conn:
        row = conn.execute(
            "SELECT create_workspace_with_founder(%s, %s, %s) AS id",
            (name.strip(), external_id, str(creator_principal_id)),
        ).fetchone()
        new_workspace_id = str(row["id"])

        conn.execute("SELECT set_config('app.workspace_id', %s, false)", (new_workspace_id,))

        audit.record_audit_event(
            conn,
            aggregate_type="membership",
            aggregate_id=creator_principal_id,
            action="created",
            actor_principal_id=creator_principal_id,
            payload={"role": "founder", "active": True},
            workspace_id=new_workspace_id,
        )

    return new_workspace_id


# ---------------------------------------------------------------------------
# Grant / change / revoke
# ---------------------------------------------------------------------------

def grant_membership(
    principal_id: str,
    role: str,
    *,
    workspace_id: str,
    actor_principal_id: str,
) -> Membership:
    """Grants a new membership, or changes an existing one's role. Upsert on the PK.

    Takes only the acting principal's id — NOT their clearance. An earlier version
    of this function took `actor_clearance: int` as a caller-supplied primitive; the
    maintainer's ruling is "client-supplied role/clearance values are untrusted",
    and that includes the ACTOR's, not only the requested role. The actor's
    clearance is resolved here, from the database, on the same connection already
    scoped to `workspace_id` — which is also what makes this the cross-workspace
    guard: `identity.resolve_principal_by_id()` raises `PrincipalNotFound` for an
    actor with no active membership in `workspace_id`, before any write is
    attempted. See the module docstring for why that must not be the audit write's
    job.

    `workspace_id` MUST be the caller's own currently-selected workspace, never a
    client-supplied value (ADR-013) — `meridian/api/workspaces.py` enforces that by
    never accepting a `workspace_id` field on the wire; it is not re-checked here.

    Anti-escalation: the actor may never grant a role whose clearance exceeds their
    own — the maintainer's ruling.
    """
    requested_clearance = _clearance_for(role)

    with store.pg(workspace_id) as conn:
        actor = identity.resolve_principal_by_id(conn, actor_principal_id, workspace_id=workspace_id)

        if requested_clearance > actor.clearance:
            raise EscalationDeniedError(
                f"cannot grant role {role!r}: exceeds the acting principal's own clearance"
            )

        row = conn.execute(
            """
            INSERT INTO membership (principal_id, workspace_id, role, clearance, active)
            VALUES (%s, %s, %s, %s, true)
            ON CONFLICT (principal_id, workspace_id) DO UPDATE
                SET role = EXCLUDED.role, clearance = EXCLUDED.clearance, active = true
            RETURNING *, (xmax = 0) AS inserted
            """,
            (principal_id, workspace_id, role, requested_clearance),
        ).fetchone()

        audit.record_audit_event(
            conn,
            aggregate_type="membership",
            aggregate_id=principal_id,
            action="created" if row["inserted"] else "updated",
            actor_principal_id=actor_principal_id,
            payload={"role": row["role"], "active": row["active"]},
            workspace_id=workspace_id,
        )

    return _row_to_membership(row)


def revoke_membership(
    principal_id: str,
    *,
    workspace_id: str,
    actor_principal_id: str,
) -> Membership:
    """Revokes a membership: `active = false`. Never a delete — see module docstring.

    Symmetric anti-escalation with `grant_membership()`: the actor's own clearance
    must cover the TARGET's current clearance, not the other way around. Without
    this, an observer could not grant a founder role but could still revoke an
    existing founder's membership outright, which is the same privilege by another
    name.

    **The target's clearance is derived from their `role`, never read from the
    stored `membership.clearance` column.** An earlier version of this function
    compared against `current["clearance"]` directly — the exact column #166 step 3
    ruled must never be read for an authorization decision. Reachable, not
    theoretical: `cli.py:125` seeds `membership.clearance` from `principal.clearance`
    independently of `principal.role`, and #182 documents fifteen fixtures where the
    two already disagree. A stale `clearance=1` beside `role='director'` (which maps
    to 3) would have let an advisor revoke a director. Caught before this reached a
    PR, by a peer reviewing the diff rather than by the test that shipped with it —
    `test_revoking_a_higher_clearance_member_is_denied`'s fixture is created by
    `grant_membership`, which writes `role` and `clearance` consistently from the
    same mapping, so the two columns AGREE by construction in that test and it
    cannot exercise the disagreement the bug depended on. Replaced with a test that
    seeds the disagreement directly through the admin connection.
    """
    with store.pg(workspace_id) as conn:
        actor = identity.resolve_principal_by_id(conn, actor_principal_id, workspace_id=workspace_id)

        current = conn.execute(
            "SELECT role, active FROM membership WHERE principal_id = %s AND workspace_id = %s",
            (principal_id, workspace_id),
        ).fetchone()
        if current is None:
            raise MembershipNotFoundError(f"no membership for {principal_id} in {workspace_id}")
        if _clearance_for(current["role"]) > actor.clearance:
            raise EscalationDeniedError(
                "cannot revoke a membership whose clearance exceeds the acting principal's own"
            )

        row = conn.execute(
            """
            UPDATE membership SET active = false
             WHERE principal_id = %s AND workspace_id = %s
            RETURNING *
            """,
            (principal_id, workspace_id),
        ).fetchone()

        audit.record_audit_event(
            conn,
            aggregate_type="membership",
            aggregate_id=principal_id,
            action="status_changed",
            actor_principal_id=actor_principal_id,
            payload={"role": row["role"], "active": False},
            workspace_id=workspace_id,
        )

    return _row_to_membership(row)
