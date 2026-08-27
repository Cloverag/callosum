"""Coverage for `principal_identity` (Meridian P3, CP-A/A1 — ADR-010).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

The load-bearing tests here are the privilege ones. `0004_app_role` sets
`ALTER DEFAULT PRIVILEGES` granting SELECT, INSERT, UPDATE and DELETE on every new
table to `callosum_app`, so the revoke in `0017` is what stands between the runtime
role and the ability to mint its own login. That is not visible in the table
definition, and it is exactly the trap `0016_audit_event` had to handle for its
append-only guarantee.
"""

import os
import uuid

import pytest

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip("set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests", allow_module_level=True)

import psycopg

from callosum import store
from callosum.config import settings

pytestmark = pytest.mark.integration

PROVIDER = "https://idp.example/"


def _admin(sql: str, params: tuple = ()) -> None:
    with psycopg.connect(settings().postgres_dsn) as conn:
        conn.execute(sql, params)
        conn.commit()


def _principal(name: str = "Identity Fixture") -> str:
    pid = str(uuid.uuid4())
    _admin(
        "INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, 'director', 2)",
        (pid, f"{name} {pid[:6]}"),
    )
    return pid


def _link(principal_id: str, subject: str, provider: str = PROVIDER) -> None:
    _admin(
        "INSERT INTO principal_identity (principal_id, provider, subject) VALUES (%s, %s, %s)",
        (principal_id, provider, subject),
    )


def _cleanup(*principal_ids: str) -> None:
    for pid in principal_ids:
        # `audit_event.actor_principal_id` references `principal(id)` ON DELETE
        # RESTRICT (0016), so a principal who has acted cannot be deleted until
        # their trail is. This teardown takes no workspace, so the delete is
        # scoped by actor rather than by workspace as the other files do —
        # which also covers events this principal wrote in a workspace this
        # test never names. Issue #170.
        _admin("DELETE FROM audit_event WHERE actor_principal_id = %s", (pid,))
        _admin("DELETE FROM principal WHERE id = %s", (pid,))


class TestTheRuntimeRoleCanReadButNotMint:
    """ADR-011: provisioning is an administrative act, not something a request does."""

    def test_login_can_resolve_a_subject(self):
        pid = _principal()
        subject = f"sub-{uuid.uuid4()}"
        _link(pid, subject)
        try:
            # Note the connection: login happens BEFORE a workspace is known, so the
            # workspace passed here is incidental — this table has no tenant predicate
            # and deliberately cannot have one.
            with store.pg(store.DEFAULT_WORKSPACE_ID) as conn:
                row = conn.execute(
                    "SELECT principal_id FROM principal_identity WHERE provider = %s AND subject = %s",
                    (PROVIDER, subject),
                ).fetchone()
            assert str(row["principal_id"]) == pid
        finally:
            _cleanup(pid)

    @pytest.mark.parametrize(
        "label,sql",
        [
            ("INSERT", "INSERT INTO principal_identity (principal_id, provider, subject) VALUES (%s, 'p', 's')"),
            ("UPDATE", "UPDATE principal_identity SET subject = 'hijacked' WHERE principal_id = %s"),
            ("DELETE", "DELETE FROM principal_identity WHERE principal_id = %s"),
        ],
    )
    def test_the_runtime_role_cannot_write(self, label, sql):
        """A runtime role that can INSERT here can grant itself any identity.

        This is the whole security value of the table: the mapping from an external
        subject to a principal is administrative data, and a request path that could
        write it would let an authenticated caller become someone else.
        """
        pid = _principal()
        _link(pid, f"sub-{uuid.uuid4()}")
        try:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with store.pg(store.DEFAULT_WORKSPACE_ID) as conn:
                    conn.execute(sql, (pid,))
        finally:
            _cleanup(pid)

    def test_the_grant_is_select_only(self):
        """Reads the catalogue rather than trusting the migration.

        `0004`'s default privileges hand out all four verbs on every new table, so if
        the revoke were ever dropped this is what would notice.
        """
        with psycopg.connect(settings().postgres_dsn) as conn:
            granted = {
                r[0]
                for r in conn.execute(
                    """
                    SELECT privilege_type FROM information_schema.role_table_grants
                     WHERE table_name = 'principal_identity' AND grantee = 'callosum_app'
                    """
                ).fetchall()
            }
        assert granted == {"SELECT"}, f"callosum_app holds {granted or 'nothing'}"


class TestTheLookupKey:
    def test_a_subject_cannot_be_claimed_twice(self):
        pid_a, pid_b = _principal("First"), _principal("Second")
        subject = f"sub-{uuid.uuid4()}"
        _link(pid_a, subject)
        try:
            # Otherwise one external identity could resolve to two people, and which
            # one you became would depend on row order.
            with pytest.raises(psycopg.errors.UniqueViolation):
                _link(pid_b, subject)
        finally:
            _cleanup(pid_a, pid_b)

    def test_the_same_subject_from_a_different_provider_is_a_different_identity(self):
        """Subjects are only unique within an issuer.

        Two providers can legitimately both issue `sub=1234`. Keying on subject alone
        would let one IdP's user resolve to another IdP's principal.
        """
        pid = _principal()
        subject = f"sub-{uuid.uuid4()}"
        _link(pid, subject, provider="https://idp-a.example/")
        try:
            _link(pid, subject, provider="https://idp-b.example/")
            with psycopg.connect(settings().postgres_dsn) as conn:
                n = conn.execute(
                    "SELECT count(*) FROM principal_identity WHERE principal_id = %s", (pid,)
                ).fetchone()[0]
            assert n == 2
        finally:
            _cleanup(pid)

    def test_one_principal_may_hold_several_identities(self):
        # The reason this is a table and not a column on `principal`.
        pid = _principal()
        _link(pid, f"sub-{uuid.uuid4()}", provider="https://idp-a.example/")
        _link(pid, f"sub-{uuid.uuid4()}", provider="https://idp-b.example/")
        try:
            with psycopg.connect(settings().postgres_dsn) as conn:
                n = conn.execute(
                    "SELECT count(*) FROM principal_identity WHERE principal_id = %s", (pid,)
                ).fetchone()[0]
            assert n == 2
        finally:
            _cleanup(pid)

    @pytest.mark.parametrize("provider,subject", [("", "s"), ("   ", "s"), ("p", ""), ("p", "  ")])
    def test_empty_provider_or_subject_is_refused(self, provider, subject):
        pid = _principal()
        try:
            with pytest.raises(psycopg.errors.CheckViolation):
                _link(pid, subject, provider=provider)
        finally:
            _cleanup(pid)


class TestLifecycle:
    def test_deleting_a_principal_removes_their_identities(self):
        """No orphans.

        A dangling identity row would let a recreated principal id silently inherit
        someone else's login.
        """
        pid = _principal()
        _link(pid, f"sub-{uuid.uuid4()}")
        _admin("DELETE FROM principal WHERE id = %s", (pid,))

        with psycopg.connect(settings().postgres_dsn) as conn:
            n = conn.execute(
                "SELECT count(*) FROM principal_identity WHERE principal_id = %s", (pid,)
            ).fetchone()[0]
        assert n == 0

    def test_an_identity_cannot_point_at_a_missing_principal(self):
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            _link(str(uuid.uuid4()), f"sub-{uuid.uuid4()}")


class TestItIsNotTenantScoped:
    def test_there_is_no_workspace_column(self):
        """ADR-010: identity is global; `membership` is what scopes.

        Mechanically necessary too — login happens before a workspace is known, so a
        tenant predicate here would have nothing to match against.
        """
        with psycopg.connect(settings().postgres_dsn) as conn:
            cols = {
                r[0]
                for r in conn.execute(
                    """
                    SELECT column_name FROM information_schema.columns
                     WHERE table_name = 'principal_identity'
                    """
                ).fetchall()
            }
        assert "workspace_id" not in cols
        assert cols == {"id", "principal_id", "provider", "subject", "created_at"}

    def test_row_level_security_is_not_enabled(self):
        # Not an oversight. A policy keyed on app.workspace_id would deny every login,
        # because no workspace is selected until after the principal is known.
        with psycopg.connect(settings().postgres_dsn) as conn:
            row = conn.execute(
                """
                SELECT relrowsecurity FROM pg_class
                 WHERE relname = 'principal_identity' AND relnamespace = 'public'::regnamespace
                """
            ).fetchone()
        assert row[0] is False
