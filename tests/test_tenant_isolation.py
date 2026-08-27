"""Live-store integration coverage for P1 multi-tenant isolation (Meridian).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``. These tests
prove the Row-Level Security lock actually holds: a connection scoped to one workspace
can never see another workspace's rows, and a connection with no workspace set sees
nothing (fail-closed). They create uniquely-tokened workspaces/documents and delete
only those records.

The RLS predicate only bites a non-superuser role, so reads/writes go through
``store.pg()`` (the ``callosum_app`` role). Setup/teardown of workspaces and the
final cleanup use the admin DSN, which bypasses RLS on purpose — it is the control
plane, not tenant traffic.
"""

import os
import uuid

import pytest

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip("set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests", allow_module_level=True)

import psycopg
from psycopg.rows import dict_row

from callosum import store
from callosum.config import settings

pytestmark = pytest.mark.integration

DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


def _admin(sql: str, params: tuple = ()) -> None:
    """Run a control-plane statement as the superuser (bypasses RLS by design)."""
    with psycopg.connect(settings().postgres_dsn) as conn:
        conn.execute(sql, params)
        conn.commit()


def _insert_doc(workspace_id: uuid.UUID, title: str, content_hash: str) -> uuid.UUID:
    # Product ingest must set workspace_id explicitly: the column DEFAULT is the Default
    # Workspace, so an unset value under a non-default session would fail the RLS
    # WITH CHECK. That is the intended, fail-closed behaviour.
    with store.pg(workspace_id=str(workspace_id)) as conn:
        return conn.execute(
            """
            INSERT INTO document (title, doc_type, raw_text, content_hash, sensitivity, workspace_id)
            VALUES (%s, 'memo', 'x', %s, 1, %s)
            RETURNING id
            """,
            (title, content_hash, str(workspace_id)),
        ).fetchone()["id"]


def _titles_visible(workspace_id: uuid.UUID | None, token: str) -> list[str]:
    with store.pg(workspace_id=str(workspace_id)) as conn:
        rows = conn.execute(
            "SELECT title FROM document WHERE content_hash LIKE %s ORDER BY title",
            (f"h%-{token}",),
        ).fetchall()
    return [r["title"] for r in rows]


def test_cross_workspace_reads_are_isolated():
    """A document created in workspace A is invisible to workspace B, and vice versa."""
    token = uuid.uuid4().hex
    wa, wb = uuid.uuid4(), uuid.uuid4()
    _admin(
        "INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s), (%s, %s, %s)",
        (wa, f"A-{token}", f"a-{token}", wb, f"B-{token}", f"b-{token}"),
    )
    doc_b = None
    try:
        _insert_doc(wa, f"docA-{token}", f"hA-{token}")
        doc_b = _insert_doc(wb, f"docB-{token}", f"hB-{token}")

        # Each workspace sees only its own document.
        assert _titles_visible(wa, token) == [f"docA-{token}"]
        assert _titles_visible(wb, token) == [f"docB-{token}"]

        # A cannot fetch B's row even when it supplies the exact id (RLS, not app filter).
        with store.pg(workspace_id=str(wa)) as conn:
            assert conn.execute("SELECT id FROM document WHERE id = %s", (doc_b,)).fetchone() is None

        # A connection with NO workspace set sees neither (fail-closed).
        with psycopg.connect(settings().postgres_app_dsn, row_factory=dict_row) as raw:
            n = raw.execute(
                "SELECT count(*) AS n FROM document WHERE content_hash LIKE %s",
                (f"h%-{token}",),
            ).fetchone()["n"]
        assert n == 0
    finally:
        # `audit_event` references `workspace(id)` ON DELETE RESTRICT (0016,
        # deliberately). This file has no shared `_cleanup`, so the line is repeated
        # at each of the four teardown sites rather than centralised — a shared
        # helper is #170's open question, not something to settle here. Issue #170.
        _admin("DELETE FROM audit_event WHERE workspace_id IN (%s, %s)", (wa, wb))
        _admin("DELETE FROM document WHERE content_hash LIKE %s", (f"h%-{token}",))
        _admin("DELETE FROM workspace WHERE id IN (%s, %s)", (wa, wb))


def test_cross_workspace_write_is_rejected():
    """Writing a row stamped for another workspace fails the RLS WITH CHECK."""
    token = uuid.uuid4().hex
    wa, wb = uuid.uuid4(), uuid.uuid4()
    _admin(
        "INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s), (%s, %s, %s)",
        (wa, f"A-{token}", f"a-{token}", wb, f"B-{token}", f"b-{token}"),
    )
    try:
        # Session scoped to A, but the row claims workspace B -> must be refused.
        with pytest.raises(psycopg.errors.Error):
            with store.pg(workspace_id=str(wa)) as conn:
                conn.execute(
                    """
                    INSERT INTO document (title, doc_type, raw_text, content_hash, sensitivity, workspace_id)
                    VALUES (%s, 'memo', 'x', %s, 1, %s)
                    """,
                    (f"smuggle-{token}", f"hX-{token}", str(wb)),
                )
    finally:
        # `audit_event` is ON DELETE RESTRICT on workspace_id — see above. Issue #170.
        _admin("DELETE FROM audit_event WHERE workspace_id IN (%s, %s)", (wa, wb))
        _admin("DELETE FROM document WHERE content_hash LIKE %s", (f"h%-{token}",))
        _admin("DELETE FROM workspace WHERE id IN (%s, %s)", (wa, wb))


def test_connection_helper_sets_workspace():
    """store.pg() defaults to the Default Workspace; an explicit id is honoured."""
    with store.pg() as conn:
        w = conn.execute("SELECT current_setting('app.workspace_id') AS w").fetchone()["w"]
    assert w == DEFAULT_WORKSPACE_ID

    other = "000000ff-0000-0000-0000-0000000000ff"
    with store.pg(workspace_id=other) as conn:
        w = conn.execute("SELECT current_setting('app.workspace_id') AS w").fetchone()["w"]
    assert w == other


def test_entity_conflict_unique_key_is_workspace_scoped():
    """The SAME conflict pair is allowed in two workspaces, but rejected twice in one.

    The UNIQUE index on entity_conflict is enforced below RLS — it sees every row — so
    before migration 0006 the same (name_a, type_a, name_b, type_b) proposed in a second
    workspace collided with the first tenant's row, coupling tenants that cannot see each
    other. 0006 adds workspace_id to the key: identity is per-workspace, collisions are
    per-workspace. This proves both directions.
    """
    token = uuid.uuid4().hex[:8]
    wa, wb = uuid.uuid4(), uuid.uuid4()
    _admin(
        "INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s), (%s, %s, %s)",
        (wa, f"A-{token}", f"a-{token}", wb, f"B-{token}", f"b-{token}"),
    )
    name_a, name_b = f"Raj-{token}", f"Rajesh-{token}"

    def _insert(ws: uuid.UUID) -> None:
        with store.pg(workspace_id=str(ws)) as conn:
            conn.execute(
                """
                INSERT INTO entity_conflict
                    (name_a, type_a, name_b, type_b, similarity, workspace_id)
                VALUES (%s, 'PERSON', %s, 'PERSON', 77.0, %s)
                """,
                (name_a, name_b, str(ws)),
            )

    try:
        # Same pair in A and in B: allowed — different workspace, different key.
        _insert(wa)
        _insert(wb)
        # Duplicate within the SAME workspace: rejected by the widened unique key.
        with pytest.raises(psycopg.errors.UniqueViolation):
            _insert(wa)
    finally:
        # `audit_event` is ON DELETE RESTRICT on workspace_id — see above. Issue #170.
        _admin("DELETE FROM audit_event WHERE workspace_id IN (%s, %s)", (wa, wb))
        _admin("DELETE FROM entity_conflict WHERE name_a = %s", (name_a,))
        _admin("DELETE FROM workspace WHERE id IN (%s, %s)", (wa, wb))


def test_control_plane_membership_is_workspace_scoped():
    """A scoped caller cannot enumerate other tenants' members (issue #32).

    Before `0011_control_plane_rls`, `membership`, `workspace`, `principal` and
    `sensitivity` carried no row-level security while `callosum_app` held full
    DML on all four. A connection scoped to one workspace could read every other
    tenant's name, member names, roles and clearance levels — no document text,
    but "who sits on which board at what clearance" is confidential in its own
    right, and P1's exit criterion requires blocking it in SQL.
    """
    wa, wb = uuid.uuid4(), uuid.uuid4()
    pa, pb = uuid.uuid4(), uuid.uuid4()
    _admin(
        "INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s), (%s, %s, %s)",
        (wa, f"ws-{wa}", str(wa), wb, f"ws-{wb}", str(wb)),
    )
    _admin(
        "INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, 'founder', 4), (%s, %s, 'founder', 4)",
        (pa, f"A-{pa}", pb, f"B-{pb}"),
    )
    _admin(
        "INSERT INTO membership (principal_id, workspace_id, role, clearance)"
        " VALUES (%s, %s, 'founder', 4), (%s, %s, 'founder', 4)",
        (pa, wa, pb, wb),
    )

    try:
        with store.pg(workspace_id=str(wa)) as conn:
            rows = conn.execute(
                "SELECT workspace_id FROM membership WHERE principal_id IN (%s, %s)", (pa, pb)
            ).fetchall()
            assert [r["workspace_id"] for r in rows] == [wa], (
                "membership leaked another tenant's row to a scoped caller"
            )

            # `workspace` is scoped on its own id, so a caller sees exactly the
            # workspace it is scoped to and cannot enumerate tenant names.
            names = conn.execute(
                "SELECT id FROM workspace WHERE id IN (%s, %s)", (wa, wb)
            ).fetchall()
            assert [r["id"] for r in names] == [wa]

            # Least privilege: the control plane is administrative. The runtime
            # role reads it and must not be able to grant itself membership.
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(
                    "INSERT INTO membership (principal_id, workspace_id, role, clearance)"
                    " VALUES (%s, %s, 'founder', 4)",
                    (pa, wa),
                )
    finally:
        # `audit_event` is ON DELETE RESTRICT on workspace_id — see above. Issue #170.
        _admin("DELETE FROM audit_event WHERE workspace_id IN (%s, %s)", (wa, wb))
        _admin("DELETE FROM membership WHERE workspace_id IN (%s, %s)", (wa, wb))
        _admin("DELETE FROM principal WHERE id IN (%s, %s)", (pa, pb))
        _admin("DELETE FROM workspace WHERE id IN (%s, %s)", (wa, wb))
