"""enable Row-Level Security on tenant tables — the fail-closed lock (Meridian P1, brick 2b.2)

This is the brick where the database itself becomes tenant-aware. Until now workspace_id
was just a stamped column nobody enforced. Here we turn on Postgres Row-Level Security so
that every read/write is silently filtered to the connection's active workspace.

For each tenant-owned table we:

  * ENABLE ROW LEVEL SECURITY  — attach the policy machinery.
  * FORCE  ROW LEVEL SECURITY  — CRITICAL: the app connects as the table's OWNER role
    (callosum), and owners bypass RLS by default. FORCE makes the policy apply to the
    owner too, otherwise this whole brick would be a silent no-op.
  * CREATE POLICY tenant_isolation — a row is visible/writable only when its workspace_id
    equals the session's app.workspace_id (set by store.pg(), brick 2b.1).

The predicate uses NULLIF(current_setting('app.workspace_id', true), '')::uuid:

  * the `true` (missing_ok) means an UNSET variable returns NULL rather than raising —
    so a connection that forgot to set a workspace sees ZERO rows (fail-closed), not an
    error and never all rows.
  * NULLIF(..., '') maps an empty string to NULL too, for the same fail-closed result.

Single-tenant safety: every existing row carries the Default Workspace id, and the frozen
path's connections set that same id, so the predicate matches every existing row and the
frozen retrieval metrics are unchanged. That equivalence is proved by brick 2b.5.

principal / workspace / membership are intentionally NOT locked: principal is global
identity, and workspace/membership are the control-plane directory the auth layer must
read *before* it knows which workspace a request belongs to.

Revision ID: 0003_enable_rls
Revises: 0002_workspace_id_columns
Create Date: 2026-07-19
"""
from alembic import op

revision = "0003_enable_rls"
down_revision = "0002_workspace_id_columns"
branch_labels = None
depends_on = None

TENANT_TABLES = [
    "document",
    "chunk",
    "node_version",
    "proposed_change",
    "extraction_failure",
    "query_log",
    "acl_grant",
]

_PREDICATE = "workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid"


def upgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
                FOR ALL
                USING ({_PREDICATE})
                WITH CHECK ({_PREDICATE})
            """
        )


def downgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
