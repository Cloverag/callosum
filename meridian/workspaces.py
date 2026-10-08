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

THE LAST-MEMBER GUARD AND THE SELF-REVOCATION FIX ARE ONE CHANGE, NOT TWO
--------------------------------------------------------------------------------
`revoke_membership()` ships two changes together (#185) that MUST NOT be split
across separate PRs, separate commits reordered, or a rebase that lands one
without the other: the last-active-membership guard, and reordering the audit
write to fix self-revocation. They are coupled, not independent, and the
coupling runs in the dangerous direction.

On merged master before this change, self-revocation of ANY member raised
`audit.ActorNotInWorkspace` — a bug (see `revoke_membership`'s own docstring) —
but that bug had an undesigned side effect: a lone founder self-revoking got a
422 and stayed active, because the audit-ordering bug fired before a workspace
could ever reach zero members. #185 was filed against that state and its
severity assumed the strand was reachable; it was not yet, by accident.

Fixing the audit-ordering bug on its own — without the guard landing in the
SAME change — would have REMOVED that accidental protection and made the
strand `#185` describes newly reachable for the first time. Shipping the two
separately would create a real commit on master where self-revocation works
and nothing stops the last member from using it, which must never be a real
state of this repository even briefly. `test_the_guard_and_the_audit_reorder_
are_one_change_not_two` pins this by asserting a lone founder's self-revocation
is refused specifically by `LastActiveMembershipError`, never by
`ActorNotInWorkspace` — the latter would mean the guard had stopped being what
does the work, silently, because the call would still fail either way.

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
`ROLE_TO_CLEARANCE` exceeds the actor's own clearance is refused outright — the
maintainer's explicit ruling. Revoking a member whose current clearance exceeds
the actor's is refused for the same reason: an actor who could not have granted
that role should not be able to strip it either, or revoke-then-regrant becomes
an escalation path the grant-side check does not close. **Originally shipped as
an unratified extension of the grant-side ruling (#186), raised with the
maintainer explicitly rather than merged as settled by implication — RATIFIED
in the same ruling that commissioned #185's last-member guard below. This is
policy, not a standing extension.**

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

import psycopg

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


class LastActiveMembershipError(WorkspaceError):
    """Refusing to revoke the last active membership in a workspace (#185).

    Named deliberately, not out of habit: `errors.py`'s name-suffix pass maps
    anything ending `NotFound` to 404, and this is not that — the membership
    exists and is found, the request is refused because of what removing it
    would do to the workspace, not because the target is missing. See
    `revoke_membership()` for why this is a different failure from
    `MembershipNotFoundError` and must stay distinguishable from it: a caller
    needs to tell "there is nothing here to revoke" apart from "there is
    something here and it cannot be revoked right now."
    """


class ApprovalNotAuthorizedError(WorkspaceError):
    """The actor is a member here, but not one who may sign off a membership grant (#225).

    Separate from `EscalationDeniedError`, which is about *clearance*. This one is about
    an authority that `ROLE_TO_CLEARANCE` deliberately does not express: `identity.py`'s
    own note on the mapping says `admin` "carries clearance 4 *and* separately carries
    membership-management authority — the two are distinct grants on one role." Conflating
    them would make any future clearance-4 role an approver by accident.
    """


class SelfApprovalDeniedError(WorkspaceError):
    """The actor filed this request and may not also sign it (#225).

    Reachable, not defensive decoration: founders and admins never produce a pending
    request (they grant directly), so at the moment of filing the requester is by
    construction not an approver — but they may be *promoted* to founder or admin while
    their own request sits in the queue, at which point approving it is a round trip from
    "may not grant this alone" to "granted it alone".
    """


class MembershipRequestNotFoundError(WorkspaceError):
    """No membership request with that id in this workspace.

    Takes the `NotFound` suffix knowingly: `errors.py`'s name pass maps it to 404, which
    is right here — unlike `LastActiveMembershipError`, this one really is "there is
    nothing at that id", and a caller's move is to re-read the queue.
    """


class MembershipRequestAlreadyDecidedError(WorkspaceError):
    """The request was already approved or rejected; it cannot be decided twice.

    Mapped explicitly to 409 in `errors.py`. It carries none of the suffixes pass 2
    recognises, so without that entry it would fall through to a 422 and tell the caller
    to fix a request that was perfectly well formed — the state refused it.
    """


class MembershipRequestAlreadyPendingError(WorkspaceError):
    """There is already an open request for this principal in this workspace.

    Enforced by `uq_membership_request_pending` (migration `0031`), a partial unique
    index, and surfaced here rather than reasoned about: the alternative — read first,
    then insert — is two statements with a window between them, and two non-admins
    submitting at once would both read "no pending request" and both insert. Letting the
    index refuse the second write is the only version that is correct under concurrency.

    Mapped explicitly to 409 in `errors.py` for the same reason as
    `MembershipRequestAlreadyDecidedError`: the request was well formed, the state
    refused it.
    """


class StaleMembershipRequestError(WorkspaceError):
    """The request is pending, but the authority it rests on has lapsed since it was filed.

    Two ways that happens, both re-checked at approval time rather than trusted from the
    moment of filing: the requester's membership was revoked, or their role was lowered
    below what they asked to grant. See `approve_membership_request()` for why an
    approver's own authority is not sufficient to cure either.

    The `Stale` prefix is load-bearing, not stylistic: `errors.py`'s pass 2 maps it to 409
    with code `stale_resource`, which is exactly the instruction a client needs — refetch
    the queue, this row is no longer actionable — and it gets there without an explicit
    registration that could be forgotten.
    """


@dataclass(frozen=True)
class MembershipRequest:
    """A read model for one `membership_request` row — a grant that is NOT in effect.

    Deliberately not a `Membership` with a flag. The two are different kinds of thing and
    the type system is where that should be visible: a `Membership` means someone has
    access, a `MembershipRequest` means someone asked. `grant_membership()` returns one or
    the other, and a caller that forgets to distinguish them gets an attribute error
    rather than a silent misreading of `active`.
    """

    id: str
    workspace_id: str
    principal_id: str
    role: str
    requested_by: str
    status: str


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


def _row_to_request(row: dict) -> MembershipRequest:
    return MembershipRequest(
        id=str(row["id"]),
        workspace_id=str(row["workspace_id"]),
        principal_id=str(row["principal_id"]),
        role=row["role"],
        requested_by=str(row["requested_by"]),
        status=row["status"],
    )


def _clearance_for(role: str) -> int:
    try:
        return identity.ROLE_TO_CLEARANCE[role]
    except KeyError:
        raise UnknownRoleError(role) from None


#: The roles that may grant a membership without a second signature, and the only roles
#: that may sign somebody else's (#225, the maintainer's requirement at the P4 signing).
#:
#: **Enumerated, not derived from clearance.** `founder` and `admin` are also the only two
#: roles at clearance 4, so `{r for r, c in ROLE_TO_CLEARANCE.items() if c == 4}` would
#: produce this same set today — and would be wrong, because it would make *any* future
#: clearance-4 role an approver silently, on the day it was added, without anyone deciding
#: that it should be. `identity.ROLE_TO_CLEARANCE`'s own comment states the distinction
#: this set depends on: "`admin` carries clearance 4 *and* separately carries
#: membership-management authority — the two are distinct grants on one role." This is the
#: second grant, and it is written down rather than inferred.
#:
#: `tests/test_membership_approval.py::test_the_approver_set_is_not_a_clearance_threshold`
#: pins that the two are distinguishable, by adding a clearance-4 role to the mapping and
#: asserting it does not become an approver.
_APPROVER_ROLES = frozenset({"founder", "admin"})


def _upsert_membership(conn, principal_id: str, role: str, workspace_id: str) -> dict:
    """The one statement that puts a membership into effect. Shared by both grant paths.

    Factored out so the direct path (`grant_membership` by a founder/admin) and the
    approved path (`approve_membership_request`) cannot drift: whatever the approval
    requirement is for, it is not for producing a *different* membership than the one a
    founder would have written. One body of SQL means that holds by construction instead
    of by two authors remembering to keep two copies the same.

    `clearance` is written from `_clearance_for(role)`, not read from a caller — the
    column is legacy and no longer read for authorization (#166 step 3), but it is still
    written on every mutation here, mirroring `cli.py:125`'s convention.
    """
    return conn.execute(
        """
        INSERT INTO membership (principal_id, workspace_id, role, clearance, active)
        VALUES (%s, %s, %s, %s, true)
        ON CONFLICT (principal_id, workspace_id) DO UPDATE
            SET role = EXCLUDED.role, clearance = EXCLUDED.clearance, active = true
        RETURNING *, (xmax = 0) AS inserted
        """,
        (principal_id, workspace_id, role, _clearance_for(role)),
    ).fetchone()


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
) -> Membership | MembershipRequest:
    """Grants a new membership, or files one for approval. See the return type (#225).

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

    **A non-approver's grant does not take effect; it is filed for approval (#225).**
    Returns a `Membership` when the actor is a `founder` or `admin` — the membership is
    live on return, exactly as before. Returns a `MembershipRequest` for every other
    role, and in that case **nothing in `membership` has changed**: the row is a claim
    waiting for an approver, and `identity.resolve_*` cannot see it because it is not a
    membership at all (migration `0031`'s docstring has the full argument for why that is
    a separate table rather than a state on the row).

    Anti-escalation still runs FIRST, before either branch. A request that could never be
    approved is not worth filing, and refusing it at submission time keeps the refusal on
    the person who made the mistake rather than surfacing it to an approver later as a
    `StaleMembershipRequestError`. It also means the clearance ceiling is enforced in
    exactly one place for both paths.
    """
    requested_clearance = _clearance_for(role)

    with store.pg(workspace_id) as conn:
        actor = identity.resolve_principal_by_id(conn, actor_principal_id, workspace_id=workspace_id)

        if requested_clearance > actor.clearance:
            raise EscalationDeniedError(
                f"cannot grant role {role!r}: exceeds the acting principal's own clearance"
            )

        if actor.role not in _APPROVER_ROLES:
            try:
                request_row = conn.execute(
                    """
                    INSERT INTO membership_request
                        (workspace_id, principal_id, role, requested_by)
                    VALUES (%s, %s, %s, %s)
                    RETURNING *
                    """,
                    (workspace_id, principal_id, role, actor_principal_id),
                ).fetchone()
            except psycopg.errors.UniqueViolation as exc:
                # `uq_membership_request_pending`. Raising out of `store.pg()` rolls the
                # transaction back, so the refusal writes no audit event — consistent
                # with `revoke_membership`'s last-member refusal, which also leaves no
                # trail. Nothing happened, so nothing is recorded as having happened.
                raise MembershipRequestAlreadyPendingError(
                    f"a membership request for {principal_id} is already awaiting approval"
                ) from exc

            # Audited at FILING, not only at decision. A request is an attempt to change
            # who can read this workspace's material, and the trail has to show the
            # attempt even if no approver ever answers it — a queue that is only audited
            # when someone acts on it loses exactly the requests nobody wanted to own.
            audit.record_audit_event(
                conn,
                aggregate_type="membership_request",
                aggregate_id=str(request_row["id"]),
                action="created",
                actor_principal_id=actor_principal_id,
                payload={
                    "role": request_row["role"],
                    "principal_id": str(request_row["principal_id"]),
                    "status": request_row["status"],
                },
                workspace_id=workspace_id,
            )
            return _row_to_request(request_row)

        row = _upsert_membership(conn, principal_id, role, workspace_id)

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

    **Refuses to revoke the last active membership in the workspace (#185, the
    maintainer's ruling — option 2, not option 1: refuse removing the LAST ACTIVE
    membership, not refuse SELF-revocation).** Option 1 targets a proxy — it would
    still let an admin strand a workspace by revoking the only OTHER member, and
    it would refuse a harmless self-revocation by someone who is not the last one
    out. Option 2 targets what actually goes wrong: a workspace with zero active
    memberships is unreachable by anything short of a superuser `UPDATE` — nothing
    in this module can resolve a principal into it (`identity.resolve_principal_
    by_id` requires an active membership), `grant_membership`/`revoke_membership`
    both resolve the actor the same way, and `create_workspace_with_founder`
    cannot target an existing workspace by design (migration 0029) — which is
    exactly the situation step 5 exists to remove.

    **The count and the update are ONE atomic statement, and this is the one place
    in this module where that matters.** The obvious shape —
    `SELECT count(*) ... ; if n <= 1: raise ...; UPDATE ...` — races: two
    concurrent revokes of two different (non-last) members can each see two active
    members, each independently decide they are not the last, and both succeed —
    leaving zero. That passes every single-threaded test written against it, which
    is what makes it dangerous rather than merely wrong. `rowcount == 0` means
    "refused, they were the last active member", decided at the instant of the
    write, not against a count read moments earlier that could already be stale.
    The next person to touch this will reach for count-then-update because it
    reads more obviously — this paragraph is why not to.

    **One statement is necessary but was NOT sufficient — the `FOR UPDATE` on the
    `EXISTS` subquery is load-bearing, and its absence is a real bug this module
    shipped with once, found by testing concurrency rather than by reasoning about
    the SQL.** A first version of this query used the `EXISTS` subquery exactly as
    written below but WITHOUT `FOR UPDATE`, on the reasoning that "one statement"
    was enough. It looked atomic, it passed every single-threaded test including
    the mutation test (disabling the whole clause correctly turned tests 2, 4 and
    5 red), and it was still racy: `UPDATE`'s row lock covers only the row being
    updated, and `EXISTS`'s inner `SELECT` — a plain, non-locking read under
    Postgres's default READ COMMITTED isolation — reads the *other* row's
    last-committed value without waiting for a concurrent transaction that has not
    committed yet. Two threads revoking two different members of a two-member
    workspace could each run their `EXISTS` check, each see the OTHER as still
    active (because neither had committed), and both proceed — reproduced directly:
    a live two-thread test against exactly that shape left 0 active members,
    consistently. Adding `FOR UPDATE` makes the `EXISTS` subquery take a real row
    lock on the "other" candidate rows, so the second transaction's `EXISTS` check
    now blocks on the first transaction's lock instead of reading past it — the
    same two-thread test run 10 times against the `FOR UPDATE` version produced
    exactly one success and one `LastActiveMembershipError` every time, winner
    alternating, no deadlocks. The lesson is not "always add `FOR UPDATE`" — it is
    that a subquery deciding whether a write is ALLOWED needs to lock what it
    reads, the same way the write itself locks what it writes, or the "one
    statement" property is cosmetic.

    Inactive rows do not count as "others exist" — the `EXISTS` subquery filters
    `active`, so a workspace whose only other memberships are already revoked
    correctly treats the remaining one as the last, not as one of several.

    **The audit write happens BEFORE the `UPDATE`, not after — reversed from
    every other mutation in this module, and deliberately.** Self-revocation is
    a real, ruled-on case (#185's own required tests: "self-revocation by a
    NON-last member succeeds" is the assertion the ruling turns on), and when
    the actor revokes THEMSELVES, the `UPDATE` deactivates the actor's own
    membership as part of the same statement that is meant to be audited.
    `record_audit_event()` requires its actor to hold an ACTIVE membership in
    the workspace (`ActorNotInWorkspace`) — a real defence elsewhere, see the
    module docstring on `create_workspace` — but writing the audit event AFTER
    the `UPDATE` would check that requirement against a row the same statement
    just deactivated, and a legitimate self-revocation would raise
    `ActorNotInWorkspace` on itself. Confirmed as a live bug, not a hypothetical
    one: self-revocation by a non-last member failed exactly this way before
    this reordering, and no test before #185 had ever exercised it — every
    existing test revoked someone OTHER than the caller. Writing the audit
    first, while the actor's own row is still active, and only then attempting
    the `UPDATE`, fixes it. Atomicity is unaffected either way: both statements
    are in the same `store.pg()` transaction, and `LastActiveMembershipError`
    below still rolls the audit write back along with everything else — test 5
    ("the audit event is written on success, not on refusal") pins exactly
    that.
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

        # Before the UPDATE — see the docstring above for why self-revocation
        # requires this order. Uses `current["role"]`, read moments ago, rather
        # than a post-update row: the role does not change on revoke, only
        # `active` does, and that new value is already known here (`False`).
        audit.record_audit_event(
            conn,
            aggregate_type="membership",
            aggregate_id=principal_id,
            action="status_changed",
            actor_principal_id=actor_principal_id,
            payload={"role": current["role"], "active": False},
            workspace_id=workspace_id,
        )

        row = conn.execute(
            """
            UPDATE membership SET active = false
             WHERE principal_id = %s AND workspace_id = %s
               AND EXISTS (
                   SELECT 1 FROM membership
                    WHERE workspace_id = %s AND active AND principal_id <> %s
                      FOR UPDATE
               )
            RETURNING *
            """,
            (principal_id, workspace_id, workspace_id, principal_id),
        ).fetchone()

        if row is None:
            # The existence check above already ruled out "no such membership" —
            # a row that vanished between the two statements would mean something
            # else deleted it, which nothing in this module does (revocation is
            # `active = false`, never a delete). So `rowcount == 0` here means
            # exactly one thing: the `EXISTS` clause found no other active member,
            # and this was the last one. Raising propagates out of `store.pg()`'s
            # `with` block, which rolls back the whole transaction — the audit
            # write above included, so a refusal leaves no trail.
            raise LastActiveMembershipError(
                f"cannot revoke {principal_id}: the last active membership in {workspace_id}"
            )

    return _row_to_membership(row)


# ---------------------------------------------------------------------------
# Approval of a non-approver's grant (#225)
# ---------------------------------------------------------------------------

def approve_membership_request(
    request_id: str,
    *,
    workspace_id: str,
    actor_principal_id: str,
) -> Membership:
    """Signs a pending request, putting the membership into effect. Returns the membership.

    The maintainer's requirement at the P4 signing (#225): a grant by any role other than
    `founder` or `admin` needs a second signature from one of those two. This is where the
    signature happens, and it is the only path that turns a `membership_request` into a
    `membership`.

    FOUR REFUSALS, AND WHY EACH IS A DIFFERENT FAILURE
    ----------------------------------------------------------------------------------
    1. **Not an approver** (`ApprovalNotAuthorizedError`, 403). Checked against
       `actor.role`, resolved from the database on the workspace-scoped connection — the
       same discipline `grant_membership` uses for clearance, for the same reason: a
       client-supplied role is untrusted, and so is the actor's own.

    2. **Self-approval** (`SelfApprovalDeniedError`, 403). #225's named requirement, and
       reachable despite looking impossible: founders and admins never *create* a pending
       request, so a request's author is never an approver at filing time — but promoting
       them while their request waits would otherwise let them sign it themselves, which
       is the whole requirement undone in two steps.

    3. **Already decided** (`MembershipRequestAlreadyDecidedError`, 409). The
       `FOR UPDATE` below is what makes this correct under concurrency rather than merely
       usually right: two approvers clicking the same queue entry serialize on the row
       lock, and the second one re-reads a committed `'approved'` instead of writing the
       membership a second time.

    4. **The requester's authority has lapsed** (`StaleMembershipRequestError`, 409) —
       the one refusal that is a decision rather than a mechanism, so it is argued rather
       than asserted.

    WHY THE REQUESTER IS RE-VALIDATED, WHEN THE APPROVER HAS FULL AUTHORITY
    ----------------------------------------------------------------------------------
    An approver is a founder or admin at clearance 4; they could have granted this role
    outright, with no request involved. So it is tempting to treat approval as the
    approver's own act and ignore what has happened to the requester since.

    That reading is wrong, and #225 says why in one clause: *"the grant does not take
    effect until a founder/admin approves it."* **The grant** — the requester's. The
    approver is a co-signatory to somebody else's act, not the author of a new one. Two
    consequences follow, and both are re-checked here rather than trusted from filing
    time:

      * **The requester must still hold an active membership.** Otherwise revoking
        somebody for cause leaves their pending requests live, to be signed later by an
        approver working through a queue with no reason to know the requester is gone.
        Revocation has to retract what the revoked member set in motion, or it is not
        revocation.

      * **The requester must still out-rank the role they asked to grant.** A demotion
        that leaves its author's pending requests approvable is the same hole one rung
        down: an exec requests `director`, is demoted to `observer` for exactly that
        reason, and the request they could no longer file today is still sitting there
        waiting to be honoured.

    This mirrors ADR-012's rule for the request path — authorization is re-derived, never
    carried — applied across time instead of across a redirect. The cost is a queue entry
    that can expire; the alternative is an authority that cannot be withdrawn.

    **The approver's own clearance is deliberately NOT re-checked against the role.**
    Both approver roles sit at clearance 4, the ceiling, so such a check could never fire
    and a test for it could never go red — the vacuous-check shape `COORDINATION.md` §5
    names. If `_APPROVER_ROLES` is ever widened to a role below 4, that check becomes
    load-bearing and must be added with it.
    """
    with store.pg(workspace_id) as conn:
        actor = identity.resolve_principal_by_id(
            conn, actor_principal_id, workspace_id=workspace_id
        )
        if actor.role not in _APPROVER_ROLES:
            raise ApprovalNotAuthorizedError(
                "only a founder or an admin may approve a membership request"
            )

        request_row = conn.execute(
            """
            SELECT * FROM membership_request
             WHERE id = %s AND workspace_id = %s
               FOR UPDATE
            """,
            (request_id, workspace_id),
        ).fetchone()
        if request_row is None:
            raise MembershipRequestNotFoundError(
                f"no membership request {request_id} in this workspace"
            )
        if request_row["status"] != "pending":
            raise MembershipRequestAlreadyDecidedError(
                f"membership request {request_id} was already {request_row['status']}"
            )

        requested_by = str(request_row["requested_by"])
        if requested_by == str(actor_principal_id):
            raise SelfApprovalDeniedError(
                "the principal who requested a membership may not approve it"
            )

        try:
            requester = identity.resolve_principal_by_id(
                conn, requested_by, workspace_id=workspace_id
            )
        except identity.PrincipalNotFound as exc:
            # Not re-raised as `PrincipalNotFound`: that maps to a 403 reading "Not
            # available to you.", which would tell an approver who IS authorized that
            # they are not. The refusal is about the request, not about them.
            raise StaleMembershipRequestError(
                "the principal who requested this membership no longer holds an active "
                "membership in this workspace"
            ) from exc

        if _clearance_for(request_row["role"]) > requester.clearance:
            raise StaleMembershipRequestError(
                f"the requester may no longer grant role {request_row['role']!r}"
            )

        row = _upsert_membership(
            conn, str(request_row["principal_id"]), request_row["role"], workspace_id
        )

        conn.execute(
            """
            UPDATE membership_request
               SET status = 'approved', decided_by = %s, decided_at = now()
             WHERE id = %s AND workspace_id = %s
            """,
            (actor_principal_id, request_id, workspace_id),
        )

        # TWO events, not one, because they answer two different questions and a reader
        # has only one of them in hand at a time.
        #
        # "How did this person get access?" is asked of the `membership` aggregate, and
        # must be answerable without knowing a request ever existed — so that row carries
        # the same shape every other grant writes, plus the two names that make this grant
        # different: who asked, and which request it was.
        #
        # "What happened to request X?" is asked of the `membership_request` aggregate.
        # Folding it into the first row would leave the queue's own history unreadable
        # except by scanning membership events and inspecting their payloads.
        #
        # The ACTOR on the membership event is the APPROVER, not the requester: the actor
        # column answers "on whose authority did this take effect", and the answer is the
        # person whose signature made it effective. The requester is named in the payload
        # rather than erased — an approved grant whose trail credits only one of the two
        # people involved is exactly the attribution gap #225 exists to close.
        audit.record_audit_event(
            conn,
            aggregate_type="membership",
            aggregate_id=str(request_row["principal_id"]),
            action="created" if row["inserted"] else "updated",
            actor_principal_id=actor_principal_id,
            payload={
                "role": row["role"],
                "active": row["active"],
                "requested_by": requested_by,
                "request_id": str(request_row["id"]),
            },
            workspace_id=workspace_id,
        )
        audit.record_audit_event(
            conn,
            aggregate_type="membership_request",
            aggregate_id=str(request_row["id"]),
            action="approved",
            actor_principal_id=actor_principal_id,
            payload={
                "role": request_row["role"],
                "principal_id": str(request_row["principal_id"]),
                "requested_by": requested_by,
            },
            workspace_id=workspace_id,
        )

    return _row_to_membership(row)


def reject_membership_request(
    request_id: str,
    *,
    workspace_id: str,
    actor_principal_id: str,
) -> MembershipRequest:
    """Refuses a pending request. Writes nothing to `membership`.

    Not a courtesy to the UI — structurally required. `uq_membership_request_pending`
    permits one open request per principal per workspace, so a request nobody answers
    blocks every future request about that principal forever. A queue has to have an exit
    that is not approval.

    **Two deliberate asymmetries with `approve_membership_request()`.**

    *No self-approval check.* Signing your own grant is self-dealing; withdrawing your own
    claim grants nothing and takes nothing from anyone, so there is no reason to refuse
    it. The check exists on the approve path because that is the only side where acting
    alone produces a privilege.

    *No staleness check.* A request whose requester was revoked or demoted is exactly the
    kind a queue needs cleared, and refusing to let an approver clear it — because the
    thing that makes it unapprovable also made it unrejectable — would wedge the grant
    path for that principal permanently. Approval has to be the strict side; rejection has
    to be the available one.

    **Still approver-only.** Rejecting is not neutral: it is the act of refusing someone
    access, and it cancels another member's decision. A requester cannot withdraw their
    own request through this path, which is a gap in the flow rather than a decision
    against it — recorded in the PR for #225. Approver-only is the fail-closed starting
    point, and widening it later is additive; narrowing it would not be.
    """
    with store.pg(workspace_id) as conn:
        actor = identity.resolve_principal_by_id(
            conn, actor_principal_id, workspace_id=workspace_id
        )
        if actor.role not in _APPROVER_ROLES:
            raise ApprovalNotAuthorizedError(
                "only a founder or an admin may reject a membership request"
            )

        request_row = conn.execute(
            """
            SELECT * FROM membership_request
             WHERE id = %s AND workspace_id = %s
               FOR UPDATE
            """,
            (request_id, workspace_id),
        ).fetchone()
        if request_row is None:
            raise MembershipRequestNotFoundError(
                f"no membership request {request_id} in this workspace"
            )
        if request_row["status"] != "pending":
            raise MembershipRequestAlreadyDecidedError(
                f"membership request {request_id} was already {request_row['status']}"
            )

        row = conn.execute(
            """
            UPDATE membership_request
               SET status = 'rejected', decided_by = %s, decided_at = now()
             WHERE id = %s AND workspace_id = %s
            RETURNING *
            """,
            (actor_principal_id, request_id, workspace_id),
        ).fetchone()

        audit.record_audit_event(
            conn,
            aggregate_type="membership_request",
            aggregate_id=str(row["id"]),
            action="rejected",
            actor_principal_id=actor_principal_id,
            payload={
                "role": row["role"],
                "principal_id": str(row["principal_id"]),
                "requested_by": str(row["requested_by"]),
            },
            workspace_id=workspace_id,
        )

    return _row_to_request(row)


def list_pending_requests(
    *,
    workspace_id: str,
    actor_principal_id: str,
) -> list[MembershipRequest]:
    """The approval queue for this workspace. Approvers only.

    **Not a clearance-filtered collection, and that is why ADR-018 does not reach it.**
    `tests/test_withheld_discipline.py` requires every domain function taking a
    `clearance` parameter to declare count-or-erase. This one takes no clearance and
    filters no rows by sensitivity: an approver sees every pending request in their
    workspace, and a non-approver sees none of it and is told so. There is no partial view
    for a reader to mistake for a complete one, which is the harm ADR-018 addresses — the
    answer is all of it or a 403, never a quiet subset.

    Deliberately all-or-nothing rather than "you may also see requests about yourself",
    which is the obvious next feature and a second disclosure rule: a pending request
    names a principal, a role, and who proposed it, and whether a non-approver may learn
    that somebody proposed a role change about them is a product decision nobody has
    taken. It is also adjacent to D7 (who may read the audit trail), still open — ADR-016's
    own disclosure argument depends on it. Fail closed until it is decided.

    Only `pending` rows. The decided ones are history, kept by the table and reachable
    through the audit trail; a queue that also lists what it has already answered stops
    being a queue.
    """
    with store.pg(workspace_id) as conn:
        actor = identity.resolve_principal_by_id(
            conn, actor_principal_id, workspace_id=workspace_id
        )
        if actor.role not in _APPROVER_ROLES:
            raise ApprovalNotAuthorizedError(
                "only a founder or an admin may read the membership approval queue"
            )

        rows = conn.execute(
            """
            SELECT * FROM membership_request
             WHERE workspace_id = %s AND status = 'pending'
             ORDER BY created_at, id
            """,
            (workspace_id,),
        ).fetchall()

    return [_row_to_request(row) for row in rows]
