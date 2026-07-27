"""Clearance resolves through membership, and `principal` is workspace-scoped (CP5b).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

P1 moved clearance from the global `principal.clearance` column onto a
per-workspace `membership` row, and the runtime never adopted it — every caller
lookup read the global column and `membership` sat empty with no readers. These
tests pin the corrected behaviour, and the fail-closed cases matter more than the
happy path: this is the input to the frozen RBAC gate in `retrieve.py`.
"""

import os
import uuid

import pytest

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip("set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests", allow_module_level=True)

import psycopg

from callosum import store
from callosum.config import settings
from callosum.identity import PrincipalNotFound, resolve_principal, resolve_principal_id

pytestmark = pytest.mark.integration


def _admin(sql: str, params: tuple = ()) -> None:
    with psycopg.connect(settings().postgres_dsn) as conn:
        conn.execute(sql, params)
        conn.commit()


def _workspace() -> str:
    ws = str(uuid.uuid4())
    _admin(
        "INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s)",
        (ws, f"id-{ws[:8]}", ws),
    )
    return ws


def _person(name: str, *, role: str = "founder", legacy_clearance: int = 4) -> str:
    pid = str(uuid.uuid4())
    _admin(
        "INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, %s, %s)",
        (pid, name, role, legacy_clearance),
    )
    return pid


def _member(principal_id: str, workspace_id: str, clearance: int, *, active: bool = True) -> None:
    _admin(
        "INSERT INTO membership (principal_id, workspace_id, role, clearance, active)"
        " VALUES (%s, %s, 'founder', %s, %s)",
        (principal_id, workspace_id, clearance, active),
    )


def _cleanup(principal_ids: list[str], workspace_ids: list[str]) -> None:
    for ws in workspace_ids:
        _admin("DELETE FROM membership WHERE workspace_id = %s", (ws,))
    for pid in principal_ids:
        _admin("DELETE FROM principal WHERE id = %s", (pid,))
    for ws in workspace_ids:
        _admin("DELETE FROM workspace WHERE id = %s", (ws,))


def test_clearance_comes_from_membership_not_the_legacy_column():
    """The membership value wins, and the two are deliberately made to disagree.

    Seeding them identically would let this pass while still reading the old
    column, which is exactly the bug being fixed.
    """
    ws = _workspace()
    pid = _person("Divergent Director", legacy_clearance=4)
    _member(pid, ws, clearance=1)
    try:
        with store.pg(ws) as conn:
            p = resolve_principal(conn, "Divergent", workspace_id=ws)
            assert p.clearance == 1, "resolver read principal.clearance, not the membership"
            assert p.workspace_id == ws
    finally:
        _cleanup([pid], [ws])


def test_no_membership_means_no_access_not_fallback_clearance():
    """A principal without a membership here does not resolve at all.

    Fail-closed: they are granted neither their global clearance nor clearance 0.
    A fallback would silently re-open the cross-tenant path this replaced.
    """
    home, elsewhere = _workspace(), _workspace()
    pid = _person("Homebound Founder", legacy_clearance=4)
    _member(pid, home, clearance=4)
    try:
        with store.pg(home) as conn:
            assert resolve_principal(conn, "Homebound", workspace_id=home).clearance == 4

        with store.pg(elsewhere) as conn:
            with pytest.raises(PrincipalNotFound):
                resolve_principal(conn, "Homebound", workspace_id=elsewhere)
    finally:
        _cleanup([pid], [home, elsewhere])


def test_inactive_membership_does_not_resolve():
    """Revoking access means deactivating the membership, and it must take effect."""
    ws = _workspace()
    pid = _person("Departed Director")
    _member(pid, ws, clearance=4, active=False)
    try:
        with store.pg(ws) as conn:
            with pytest.raises(PrincipalNotFound):
                resolve_principal(conn, "Departed", workspace_id=ws)
    finally:
        _cleanup([pid], [ws])


def test_principal_rows_are_invisible_from_another_workspace():
    """`principal` itself is now RLS-scoped through membership (0013).

    Closes the residual gap left by `p1.0.5`, which could not apply this policy
    while `membership` was empty.
    """
    home, elsewhere = _workspace(), _workspace()
    pid = _person("Scoped Person")
    _member(pid, home, clearance=3)
    try:
        with store.pg(home) as conn:
            assert conn.execute(
                "SELECT count(*) AS n FROM principal WHERE id = %s", (uuid.UUID(pid),)
            ).fetchone()["n"] == 1

        with store.pg(elsewhere) as conn:
            assert conn.execute(
                "SELECT count(*) AS n FROM principal WHERE id = %s", (uuid.UUID(pid),)
            ).fetchone()["n"] == 0, "principal leaked across workspaces"
    finally:
        _cleanup([pid], [home, elsewhere])


def test_runtime_role_cannot_create_people():
    """Identity creation is administrative; `callosum init` moved to the admin path."""
    ws = _workspace()
    try:
        with store.pg(ws) as conn:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(
                    "INSERT INTO principal (name, role, clearance) VALUES ('Intruder', 'founder', 4)"
                )
    finally:
        _cleanup([], [ws])


def test_reviewer_id_resolution_is_also_membership_scoped():
    """Attribution lookups are scoped too, so a foreign name cannot be recorded here."""
    home, elsewhere = _workspace(), _workspace()
    pid = _person("Reviewer Person")
    _member(pid, home, clearance=2)
    try:
        with store.pg(home) as conn:
            assert str(resolve_principal_id(conn, "Reviewer", workspace_id=home)) == pid
        with store.pg(elsewhere) as conn:
            assert resolve_principal_id(conn, "Reviewer", workspace_id=elsewhere) is None
    finally:
        _cleanup([pid], [home, elsewhere])
