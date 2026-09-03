"""Workspace bootstrap and membership grant/revoke (P4 criterion 1, #166 step 5).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

The boundary, not the happy path — issue #166 comment 5530505507 lists the required
tests A through H; each is named after the letter it corresponds to there.
"""

import os
import uuid

import pytest

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip("set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests", allow_module_level=True)

import psycopg
from psycopg.rows import dict_row

from callosum import identity, store
from callosum.config import settings
from meridian import workspaces

pytestmark = pytest.mark.integration


def _admin(sql: str, params: tuple = ()) -> None:
    with psycopg.connect(settings().postgres_dsn, row_factory=dict_row) as conn:
        conn.execute(sql, params)
        conn.commit()


def _admin_fetch(sql: str, params: tuple = ()) -> list:
    with psycopg.connect(settings().postgres_dsn, row_factory=dict_row) as conn:
        return conn.execute(sql, params).fetchall()


def _principal(role: str = "director", clearance: int | None = None, name: str = "Test Principal") -> str:
    """A `principal` row via the admin connection. `callosum_app` cannot write this
    table (see `test_the_app_connection_cannot_insert_into_workspace_directly`'s
    sibling restriction on `principal` — 0013), so every fixture in this file goes
    through here, the same as `test_minutes_api.py`'s `_principal_with_identity`.

    `clearance` defaults to the role-mapped value (`identity.ROLE_TO_CLEARANCE`),
    not a hand-written number paired with `role` and hoped to agree with it — #181
    applied the same fix to 57 fixtures across 26 files after a hand-paired
    role/clearance literal drifted silently (#182 catalogues 15 that still do, in
    files this rewrite did not touch). Pass `clearance` explicitly only to
    construct a DELIBERATELY disagreeing row, which is a real thing this file needs
    once — `test_revoking_a_higher_clearance_member_is_denied` seeds one directly
    through `_admin` rather than through this helper, because a disagreeing row is
    exactly what that test is for and this default must not quietly launder it back
    into agreement.
    """
    pid = str(uuid.uuid4())
    resolved_clearance = clearance if clearance is not None else identity.ROLE_TO_CLEARANCE[role]
    _admin(
        "INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, %s, %s)",
        (pid, name, role, resolved_clearance),
    )
    return pid


def _cleanup(*, workspace_ids: list = (), principal_ids: list = ()) -> None:
    """Skips falsy ids.

    Every test below assigns its workspace/principal ids inside `try` and cleans up
    in `finally`, with the name initialised to `None` beforehand. If the creation
    call itself raises, an uninitialised name would turn `finally`'s own
    `NameError` into the reported failure instead of the real one — initialising to
    `None` avoids the `NameError`, and skipping falsy ids here is what makes that
    safe to do without cleanup itself failing on a `None`.
    """
    for ws in workspace_ids:
        if not ws:
            continue
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM membership WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM workspace WHERE id = %s", (ws,))
    for pid in principal_ids:
        if not pid:
            continue
        _admin("DELETE FROM principal WHERE id = %s", (pid,))


class TestBootstrap:
    def test_creating_a_workspace_yields_exactly_one_founder_membership(self):
        """A. The count, not just existence — a second row would be silent over-grant."""
        founder = _principal()
        ws = None
        try:
            ws = workspaces.create_workspace("Boundary Test WS", None, founder)

            rows = _admin_fetch("SELECT * FROM membership WHERE workspace_id = %s", (ws,))
            assert len(rows) == 1
            assert rows[0]["principal_id"] == uuid.UUID(founder)
            assert rows[0]["role"] == "founder"
            assert rows[0]["active"] is True
        finally:
            _cleanup(workspace_ids=[ws], principal_ids=[founder])

    def test_the_bootstrap_itself_is_audited(self):
        """Step 6 is 'audit writes on every membership mutation,' and bootstrap is
        the first membership mutation there is. `test_every_mutation_is_audited`
        (in `TestGrantAndRevoke`) filters on a GRANTED member's `aggregate_id` and
        never looks at the founder's own event — the one `create_workspace` itself
        writes. This is the one place that gets checked.
        """
        founder = _principal()
        ws = None
        try:
            ws = workspaces.create_workspace("Audited Bootstrap", None, founder)
            events = _admin_fetch(
                "SELECT action, actor_principal_id, payload FROM audit_event"
                " WHERE workspace_id = %s AND aggregate_type = 'membership' AND aggregate_id = %s",
                (ws, founder),
            )
            assert len(events) == 1
            assert events[0]["action"] == "created"
            assert str(events[0]["actor_principal_id"]) == founder
            assert events[0]["payload"]["role"] == "founder"
        finally:
            _cleanup(workspace_ids=[ws], principal_ids=[founder])

    def test_the_function_has_no_workspace_id_parameter(self):
        """B. Structural, against `pg_proc` — so adding a parameter later fails this
        test rather than only being caught if someone happens to read the SQL.
        """
        rows = _admin_fetch(
            """
            SELECT p.proargnames, p.proargtypes
              FROM pg_proc p
             WHERE p.proname = 'create_workspace_with_founder'
            """
        )
        assert len(rows) == 1
        argnames = rows[0]["proargnames"]
        assert argnames == ["p_name", "p_external_id", "p_principal_id"]
        assert not any("workspace" in str(n).lower() and "id" in str(n).lower() for n in argnames)

    def test_public_holds_no_execute_on_the_bootstrap_function(self):
        """Structural, same family as B. Postgres grants function EXECUTE to PUBLIC
        by DEFAULT (unlike tables, which start with nothing granted) — so the
        `REVOKE ALL ... FROM PUBLIC` in 0029 is load-bearing, not redundant. This
        pins it against the catalogue so the next reader cannot mistake it for
        belt-and-braces and remove it. `callosum_app` must still hold EXECUTE, or
        the route this exists for stops working entirely.
        """
        rows = _admin_fetch(
            """
            SELECT has_function_privilege('public', 'create_workspace_with_founder(text,text,uuid)', 'EXECUTE') AS public_can,
                   has_function_privilege('callosum_app', 'create_workspace_with_founder(text,text,uuid)', 'EXECUTE') AS app_can
            """
        )
        assert rows[0]["public_can"] is False
        assert rows[0]["app_can"] is True

    def test_the_function_is_security_definer_owned_by_a_bypassrls_role(self):
        """Structural, same family as B. This is the property the whole design
        rests on: a `SECURITY DEFINER` function owned by a role WITHOUT
        `rolbypassrls` would still exist, still be granted, and would silently
        fail against `workspace`/`membership`'s `FORCE ROW LEVEL SECURITY` instead
        of bypassing it — a failure that would look like a bug in the route, not a
        misconfigured migration. `CREATE FUNCTION` takes its owner from whoever
        executes the migration, which nothing else in this suite checks.
        """
        rows = _admin_fetch(
            """
            SELECT p.prosecdef, r.rolbypassrls
              FROM pg_proc p JOIN pg_roles r ON r.oid = p.proowner
             WHERE p.proname = 'create_workspace_with_founder'
            """
        )
        assert len(rows) == 1
        assert rows[0]["prosecdef"] is True
        assert rows[0]["rolbypassrls"] is True

    def test_the_app_connection_cannot_insert_into_workspace_directly(self):
        """C. `workspace` stays fully revoked; only the SECURITY DEFINER function may write it."""
        with store.pg(store.DEFAULT_WORKSPACE_ID) as conn:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(
                    "INSERT INTO workspace (name, external_id) VALUES ('nope', %s)",
                    (f"nope-{uuid.uuid4()}",),
                )

    def test_the_app_connection_cannot_insert_a_membership_outside_the_selected_workspace(self):
        """D. RLS WITH CHECK, not the grant — 0029 gives `callosum_app` INSERT on
        `membership` in general; the tenant policy is what stops it naming a
        DIFFERENT workspace than the one its session is scoped to.
        """
        founder = _principal()
        target = _principal()
        mine = theirs = None
        try:
            mine = workspaces.create_workspace("Mine", None, founder)
            theirs = workspaces.create_workspace("Theirs", None, _principal())

            with store.pg(mine) as conn:
                with pytest.raises(psycopg.errors.InsufficientPrivilege) as exc_info:
                    conn.execute(
                        "INSERT INTO membership (principal_id, workspace_id, role, clearance, active)"
                        " VALUES (%s, %s, 'founder', 4, true)",
                        (target, theirs),
                    )
                assert "row-level security" in str(exc_info.value).lower()
        finally:
            _cleanup(workspace_ids=[mine, theirs], principal_ids=[founder, target])

    def test_a_failed_creation_leaves_no_orphan_workspace_or_membership(self):
        """H. `p_principal_id` that does not exist: the membership INSERT violates
        its FK, and `pytest.raises` below is the actual proof this test provides.

        The two `assert ... == []` are a regression guard, not evidence of the
        current design — an earlier version of this docstring described them as
        proof, and that claim does not survive checking. Postgres rolls back a
        failed statement regardless of how well the function inside it is written,
        and a single `SELECT` calling a FUNCTION (never a PROCEDURE) cannot COMMIT
        partway through — there is no version of this function, reachable this
        way, that COULD leave an orphan, so these two asserts cannot fail today.
        They earn their place the day someone converts this to a PROCEDURE with an
        internal COMMIT, which genuinely could orphan a workspace row.

        The real mutant is on `pytest.raises` itself: wrapping the membership
        INSERT in an `EXCEPTION WHEN foreign_key_violation THEN ...` block that
        swallows the error turns this red (`Failed: DID NOT RAISE`) without
        touching either assert below. Mutation-tested against the live function
        and reverted via `alembic downgrade`/`upgrade` rather than left in this
        file — see the PR for the output.
        """
        ghost = str(uuid.uuid4())
        external_id = f"ghost-{uuid.uuid4()}"

        with store.pg(store.DEFAULT_WORKSPACE_ID) as conn:
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                conn.execute(
                    "SELECT create_workspace_with_founder(%s, %s, %s)",
                    ("Ghost WS", external_id, ghost),
                )

        assert _admin_fetch("SELECT * FROM workspace WHERE external_id = %s", (external_id,)) == []
        assert _admin_fetch("SELECT * FROM membership WHERE principal_id = %s", (ghost,)) == []

    def test_a_workspace_without_its_founder_membership_makes_its_creator_unresolvable(self):
        """H, the stronger form. `principal`'s RLS is membership-derived (0013): a
        principal with no active membership in the current workspace is invisible
        there, not merely unauthorized. Simulated directly (not through the
        function, which cannot produce this state) to show why H matters: a
        workspace whose founder membership failed to land is not a workspace with
        one thing missing, it is a workspace nobody can resolve a principal in.
        """
        orphan_principal = _principal()
        # A workspace with no membership at all — admin-created, bypassing the
        # function on purpose, to reach a state the function itself refuses to
        # produce.
        ws = str(uuid.uuid4())
        _admin(
            "INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s)",
            (ws, "No Founder", f"no-founder-{ws[:8]}"),
        )
        try:
            with store.pg(ws) as conn:
                visible = conn.execute(
                    "SELECT id FROM principal WHERE id = %s", (orphan_principal,)
                ).fetchall()
            assert visible == []
        finally:
            _cleanup(workspace_ids=[ws], principal_ids=[orphan_principal])

    def test_hardcoded_founder_clearance_matches_the_role_mapping(self):
        """The clearance point. Read back from a real membership row, not from the
        migration's source text — the same idiom as
        `test_audit.py::test_the_sql_check_and_the_python_frozensets_agree`.
        """
        founder = _principal()
        ws = None
        try:
            ws = workspaces.create_workspace("Clearance Agreement", None, founder)
            row = _admin_fetch(
                "SELECT clearance FROM membership WHERE workspace_id = %s AND principal_id = %s",
                (ws, founder),
            )[0]
            assert row["clearance"] == identity.ROLE_TO_CLEARANCE["founder"]
        finally:
            _cleanup(workspace_ids=[ws], principal_ids=[founder])


class TestGrantAndRevoke:
    def test_founder_granting_a_lower_or_equal_role_is_allowed(self):
        """E."""
        founder = _principal()
        newcomer = _principal(role="observer")
        ws = None
        try:
            ws = workspaces.create_workspace("Grant Lower", None, founder)

            granted = workspaces.grant_membership(
                newcomer, "advisor",
                workspace_id=ws, actor_principal_id=founder,
            )
            assert granted.role == "advisor"
            assert granted.clearance == identity.ROLE_TO_CLEARANCE["advisor"]
            assert granted.active is True

            equal = workspaces.grant_membership(
                newcomer, "founder",
                workspace_id=ws, actor_principal_id=founder,
            )
            assert equal.role == "founder"
        finally:
            _cleanup(workspace_ids=[ws], principal_ids=[founder, newcomer])

    def test_founder_attempting_a_higher_clearance_role_is_denied(self):
        """F. A clearance-3 actor cannot grant `founder` (clearance 4).

        `founder`, not `director`, creates the workspace. `create_workspace()`
        always grants clearance 4 to whoever calls it, regardless of their global
        `principal.role`/`principal.clearance` — so a `director` fixture that
        CREATED the workspace would actually hold clearance 4 there (as its
        founder), and this test would assert nothing. The clearance-3 actor has to
        be GRANTED `director` inside a workspace someone else founded, the same way
        a real one would come to exist.
        """
        founder = _principal()
        director = _principal()
        newcomer = _principal()
        ws = None
        try:
            ws = workspaces.create_workspace("Grant Higher", None, founder)
            workspaces.grant_membership(
                director, "director", workspace_id=ws, actor_principal_id=founder,
            )

            with pytest.raises(workspaces.EscalationDeniedError):
                workspaces.grant_membership(
                    newcomer, "founder",
                    workspace_id=ws, actor_principal_id=director,
                )

            # Refused before any write: no membership row exists for the target.
            rows = _admin_fetch(
                "SELECT 1 FROM membership WHERE principal_id = %s AND workspace_id = %s",
                (newcomer, ws),
            )
            assert rows == []
        finally:
            _cleanup(workspace_ids=[ws], principal_ids=[founder, director, newcomer])

    def test_a_cross_workspace_grant_is_denied(self):
        """G.

        `grant_membership(workspace_id=...)` takes the target workspace as a plain
        argument — the API route enforces "always the caller's own `CurrentWorkspace`,
        never a client-supplied value" by construction (`MembershipGrant` has no
        `workspace_id` field at all). This test calls the domain function directly,
        as if that structural guarantee were bypassed, to check there is a SECOND,
        independent refusal underneath it.

        There is, but not the one an RLS-first intuition predicts, and not (as an
        earlier version of both this function and this test assumed) a side effect
        of the audit write. `store.pg(ws_b)` scopes the session to `ws_b`, and the
        target row's own `workspace_id` is also `ws_b` — so `membership`'s WITH
        CHECK sees no mismatch and the INSERT would succeed on its own (proven by
        `test_the_app_connection_cannot_insert_a_membership_outside_the_selected_
        workspace`, which puts the mismatch on the SQL statement itself rather than
        on the calling principal).

        What actually refuses this call is `grant_membership` resolving the actor
        FIRST, on the connection already scoped to `ws_b`:
        `identity.resolve_principal_by_id(conn, founder_a, workspace_id=ws_b)`
        raises `PrincipalNotFound` because `founder_a` holds no active membership in
        `ws_b` — before any write is attempted. This is on the authorization path,
        not the logging path: it holds even if the audit write were removed,
        batched, or moved after commit, which the earlier `ActorNotInWorkspace`-via-
        audit version did not.
        """
        founder_a = _principal()
        target = _principal()
        ws_a = ws_b = None
        try:
            ws_a = workspaces.create_workspace("Cross A", None, founder_a)
            ws_b = workspaces.create_workspace("Cross B", None, _principal())

            with pytest.raises(identity.PrincipalNotFound):
                workspaces.grant_membership(
                    target, "observer",
                    workspace_id=ws_b, actor_principal_id=founder_a,
                )

            survivors = _admin_fetch(
                "SELECT 1 FROM membership WHERE principal_id = %s AND workspace_id = %s",
                (target, ws_b),
            )
            assert survivors == []
        finally:
            _cleanup(workspace_ids=[ws_a, ws_b], principal_ids=[founder_a, target])

    def test_revoking_sets_active_false_not_a_delete(self):
        founder = _principal()
        member = _principal(role="observer")
        ws = None
        try:
            ws = workspaces.create_workspace("Revoke", None, founder)
            workspaces.grant_membership(
                member, "advisor", workspace_id=ws, actor_principal_id=founder,
            )

            revoked = workspaces.revoke_membership(
                member, workspace_id=ws, actor_principal_id=founder,
            )
            assert revoked.active is False
            assert revoked.role == "advisor"

            row = _admin_fetch(
                "SELECT active FROM membership WHERE principal_id = %s AND workspace_id = %s",
                (member, ws),
            )[0]
            assert row["active"] is False
        finally:
            _cleanup(workspace_ids=[ws], principal_ids=[founder, member])

    def test_revoking_a_higher_clearance_member_is_denied(self):
        """Symmetric extension of F for revoke — see the module docstring in
        workspaces.py for why this exists though the ruling only stated the grant
        half.

        The target's membership is seeded through the admin connection with
        `role='director'` (clearance 3 via the mapping) but a STORED `clearance` of
        1 — a deliberately disagreeing row, the same shape #182 documents in
        fifteen other fixtures, and confirmed legal at the schema level: `role` and
        `clearance` are constrained independently (`membership_role_check` on the
        vocabulary, `membership_clearance_fkey` on the 0-4 ladder), and nothing
        ties the two columns to each other. `grant_membership()` cannot produce
        this state itself — it always writes `role` and `clearance` together from
        the same mapping — so a target created through it could never demonstrate
        the bug an earlier version of `revoke_membership` had (comparing against
        the stored column instead of the role-derived value). Seeded directly
        through `_admin`, bypassing `_principal()`'s own now-consistent default,
        specifically to construct the disagreement that bug depended on.
        """
        founder = _principal()
        advisor = _principal(role="advisor")
        director = _principal(role="director")
        ws = None
        try:
            ws = workspaces.create_workspace("Revoke Higher", None, founder)
            workspaces.grant_membership(
                advisor, "advisor", workspace_id=ws, actor_principal_id=founder,
            )
            _admin(
                "INSERT INTO membership (principal_id, workspace_id, role, clearance, active)"
                " VALUES (%s, %s, 'director', 1, true)",
                (director, ws),
            )

            # An advisor (clearance 2) revoking a stored-clearance-1 "director": the
            # column alone would allow it, the role (clearance 3) must not.
            with pytest.raises(workspaces.EscalationDeniedError):
                workspaces.revoke_membership(
                    director, workspace_id=ws, actor_principal_id=advisor,
                )

            row = _admin_fetch(
                "SELECT active FROM membership WHERE principal_id = %s AND workspace_id = %s",
                (director, ws),
            )[0]
            assert row["active"] is True
        finally:
            _cleanup(workspace_ids=[ws], principal_ids=[founder, advisor, director])

    def test_an_unrecognised_role_is_refused_before_any_write(self):
        founder = _principal()
        target = _principal()
        ws = None
        try:
            ws = workspaces.create_workspace("Bad Role", None, founder)
            with pytest.raises(workspaces.UnknownRoleError):
                workspaces.grant_membership(
                    target, "superuser",
                    workspace_id=ws, actor_principal_id=founder,
                )
            rows = _admin_fetch(
                "SELECT 1 FROM membership WHERE principal_id = %s AND workspace_id = %s",
                (target, ws),
            )
            assert rows == []
        finally:
            _cleanup(workspace_ids=[ws], principal_ids=[founder, target])

    def test_every_mutation_is_audited(self):
        """Grant, change and revoke each leave a `membership` audit event naming the
        actor. The bootstrap grant itself is checked separately —
        `TestBootstrap.test_the_bootstrap_itself_is_audited` — because it is not
        one of THIS member's events; it is the founder's own, written by
        `create_workspace()` before this member exists.
        """
        founder = _principal()
        member = _principal(role="observer")
        ws = None
        try:
            ws = workspaces.create_workspace("Audited", None, founder)
            workspaces.grant_membership(
                member, "advisor", workspace_id=ws, actor_principal_id=founder,
            )
            workspaces.grant_membership(
                member, "director", workspace_id=ws, actor_principal_id=founder,
            )
            workspaces.revoke_membership(
                member, workspace_id=ws, actor_principal_id=founder,
            )

            events = _admin_fetch(
                "SELECT action, actor_principal_id FROM audit_event"
                " WHERE workspace_id = %s AND aggregate_type = 'membership' AND aggregate_id = %s"
                " ORDER BY created_at",
                (ws, member),
            )
            assert [e["action"] for e in events] == ["created", "updated", "status_changed"]
            assert all(str(e["actor_principal_id"]) == founder for e in events)
        finally:
            _cleanup(workspace_ids=[ws], principal_ids=[founder, member])
