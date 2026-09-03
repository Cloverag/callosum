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
from meridian import audit, workspaces

pytestmark = pytest.mark.integration


def _admin(sql: str, params: tuple = ()) -> None:
    with psycopg.connect(settings().postgres_dsn, row_factory=dict_row) as conn:
        conn.execute(sql, params)
        conn.commit()


def _admin_fetch(sql: str, params: tuple = ()) -> list:
    with psycopg.connect(settings().postgres_dsn, row_factory=dict_row) as conn:
        return conn.execute(sql, params).fetchall()


def _principal(role: str = "director", clearance: int = 3, name: str = "Test Principal") -> str:
    """A `principal` row via the admin connection. `callosum_app` cannot write this
    table (see `test_the_app_connection_cannot_insert_into_workspace_directly`'s
    sibling restriction on `principal` — 0013), so every fixture in this file goes
    through here, the same as `test_minutes_api.py`'s `_principal_with_identity`.
    """
    pid = str(uuid.uuid4())
    _admin(
        "INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, %s, %s)",
        (pid, name, role, clearance),
    )
    return pid


def _cleanup(*, workspace_ids: list[str] = (), principal_ids: list[str] = ()) -> None:
    for ws in workspace_ids:
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM membership WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM workspace WHERE id = %s", (ws,))
    for pid in principal_ids:
        _admin("DELETE FROM principal WHERE id = %s", (pid,))


class TestBootstrap:
    def test_creating_a_workspace_yields_exactly_one_founder_membership(self):
        """A. The count, not just existence — a second row would be silent over-grant."""
        founder = _principal()
        try:
            ws = workspaces.create_workspace("Boundary Test WS", None, founder)

            rows = _admin_fetch("SELECT * FROM membership WHERE workspace_id = %s", (ws,))
            assert len(rows) == 1
            assert rows[0]["principal_id"] == uuid.UUID(founder)
            assert rows[0]["role"] == "founder"
            assert rows[0]["active"] is True
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
        """H. `p_principal_id` that does not exist: the workspace insert succeeds,
        the membership insert violates its FK, and the whole statement — both
        inserts, one PL/pgSQL function body — rolls back together.
        """
        ghost = str(uuid.uuid4())
        external_id = f"ghost-{uuid.uuid4()}"

        with store.pg(store.DEFAULT_WORKSPACE_ID) as conn:
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                conn.execute(
                    "SELECT create_workspace_with_founder(%s, %s, %s)",
                    ("Ghost WS", external_id, ghost),
                )

        survivors = _admin_fetch("SELECT * FROM workspace WHERE external_id = %s", (external_id,))
        assert survivors == []

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
        newcomer = _principal(role="observer", clearance=0)
        try:
            ws = workspaces.create_workspace("Grant Lower", None, founder)

            granted = workspaces.grant_membership(
                newcomer, "advisor",
                workspace_id=ws, actor_principal_id=founder, actor_clearance=4,
            )
            assert granted.role == "advisor"
            assert granted.clearance == identity.ROLE_TO_CLEARANCE["advisor"]
            assert granted.active is True

            equal = workspaces.grant_membership(
                newcomer, "founder",
                workspace_id=ws, actor_principal_id=founder, actor_clearance=4,
            )
            assert equal.role == "founder"
        finally:
            _cleanup(workspace_ids=[ws], principal_ids=[founder, newcomer])

    def test_founder_attempting_a_higher_clearance_role_is_denied(self):
        """F. A clearance-3 actor cannot grant `founder` (clearance 4)."""
        director = _principal(role="director", clearance=3)
        newcomer = _principal(role="observer", clearance=0)
        try:
            ws = workspaces.create_workspace("Grant Higher", None, director)

            with pytest.raises(workspaces.EscalationDeniedError):
                workspaces.grant_membership(
                    newcomer, "founder",
                    workspace_id=ws, actor_principal_id=director, actor_clearance=3,
                )

            # Refused before any write: no membership row exists for the target.
            rows = _admin_fetch(
                "SELECT 1 FROM membership WHERE principal_id = %s AND workspace_id = %s",
                (newcomer, ws),
            )
            assert rows == []
        finally:
            _cleanup(workspace_ids=[ws], principal_ids=[director, newcomer])

    def test_a_cross_workspace_grant_is_denied(self):
        """G.

        `grant_membership(workspace_id=...)` takes the target workspace as a plain
        argument — the API route enforces "always the caller's own `CurrentWorkspace`,
        never a client-supplied value" by construction (`MembershipGrant` has no
        `workspace_id` field at all). This test calls the domain function directly,
        as if that structural guarantee were bypassed, to check there is a SECOND,
        independent refusal underneath it.

        There is, but not the one an RLS-first intuition predicts. `store.pg(ws_b)`
        scopes the session to `ws_b`, and the target row's own `workspace_id` is
        also `ws_b` — so `membership`'s WITH CHECK sees no mismatch and the INSERT
        actually succeeds (proven by `test_the_app_connection_cannot_insert_a_
        membership_outside_the_selected_workspace`, which puts the mismatch on the
        SQL statement itself rather than on the calling principal). What refuses
        this call is `record_audit_event`'s own membership check: `founder_a` has
        no ACTIVE membership in `ws_b`, so writing the audit trail raises
        `ActorNotInWorkspace` — and because that happens inside the same
        `store.pg()` transaction as the INSERT, the whole thing rolls back with it.
        Asserted below, not assumed: no membership row survives for `target` in
        `ws_b` afterwards.
        """
        founder_a = _principal()
        target = _principal()
        try:
            ws_a = workspaces.create_workspace("Cross A", None, founder_a)
            ws_b = workspaces.create_workspace("Cross B", None, _principal())

            with pytest.raises(audit.ActorNotInWorkspace):
                workspaces.grant_membership(
                    target, "observer",
                    workspace_id=ws_b, actor_principal_id=founder_a, actor_clearance=4,
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
        member = _principal(role="observer", clearance=0)
        try:
            ws = workspaces.create_workspace("Revoke", None, founder)
            workspaces.grant_membership(
                member, "advisor", workspace_id=ws, actor_principal_id=founder, actor_clearance=4,
            )

            revoked = workspaces.revoke_membership(
                member, workspace_id=ws, actor_principal_id=founder, actor_clearance=4,
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
        """
        founder = _principal()
        director = _principal(role="director", clearance=3)
        try:
            ws = workspaces.create_workspace("Revoke Higher", None, founder)
            workspaces.grant_membership(
                director, "director", workspace_id=ws, actor_principal_id=founder, actor_clearance=4,
            )

            with pytest.raises(workspaces.EscalationDeniedError):
                workspaces.revoke_membership(
                    founder, workspace_id=ws, actor_principal_id=director, actor_clearance=3,
                )

            row = _admin_fetch(
                "SELECT active FROM membership WHERE principal_id = %s AND workspace_id = %s",
                (founder, ws),
            )[0]
            assert row["active"] is True
        finally:
            _cleanup(workspace_ids=[ws], principal_ids=[founder, director])

    def test_an_unrecognised_role_is_refused_before_any_write(self):
        founder = _principal()
        target = _principal()
        try:
            ws = workspaces.create_workspace("Bad Role", None, founder)
            with pytest.raises(workspaces.UnknownRoleError):
                workspaces.grant_membership(
                    target, "superuser",
                    workspace_id=ws, actor_principal_id=founder, actor_clearance=4,
                )
            rows = _admin_fetch(
                "SELECT 1 FROM membership WHERE principal_id = %s AND workspace_id = %s",
                (target, ws),
            )
            assert rows == []
        finally:
            _cleanup(workspace_ids=[ws], principal_ids=[founder, target])

    def test_every_mutation_is_audited(self):
        """Grant, change and revoke each leave a `membership` audit event naming the actor."""
        founder = _principal()
        member = _principal(role="observer", clearance=0)
        try:
            ws = workspaces.create_workspace("Audited", None, founder)
            workspaces.grant_membership(
                member, "advisor", workspace_id=ws, actor_principal_id=founder, actor_clearance=4,
            )
            workspaces.grant_membership(
                member, "director", workspace_id=ws, actor_principal_id=founder, actor_clearance=4,
            )
            workspaces.revoke_membership(
                member, workspace_id=ws, actor_principal_id=founder, actor_clearance=4,
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
