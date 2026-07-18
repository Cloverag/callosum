"""add workspace_id to tenant tables + backfill Default Workspace (Meridian P1, brick 2a)

Stamps every tenant-owned table with a `workspace_id`. It is added `NOT NULL DEFAULT
<Default Workspace>`, which does two things at once:

  * Postgres backfills every EXISTING row with the Default Workspace automatically.
  * The frozen ingest/eval code — which inserts rows WITHOUT mentioning workspace_id —
    keeps working unchanged, because the column supplies its own default.

This brick deliberately does NOT enable Row-Level Security. The lock (RLS) is the next
brick, together with connection-context plumbing (`SET app.workspace_id`) and the
per-tenant negative tests. Until then this is a pure, reversible additive change and
the frozen retrieval behaviour is unaffected.

Note for the multi-tenant future: once product ingest sets workspace_id explicitly, the
DEFAULT should be DROPPED so a forgotten workspace_id becomes a loud error instead of
silently landing data in the Default Workspace.

Revision ID: 0002_workspace_id_columns
Revises: 0001_workspace_membership
Create Date: 2026-07-18
"""
from alembic import op

revision = "0002_workspace_id_columns"
down_revision = "0001_workspace_membership"
branch_labels = None
depends_on = None

DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"

# principal is intentionally excluded: it is a GLOBAL identity. A person's
# workspace scoping lives on the membership edge, not on the person.
TENANT_TABLES = [
    "document",
    "chunk",
    "node_version",
    "proposed_change",
    "extraction_failure",
    "query_log",
    "acl_grant",
]


def upgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(
            f"""
            ALTER TABLE {table}
                ADD COLUMN workspace_id UUID NOT NULL
                DEFAULT '{DEFAULT_WORKSPACE_ID}'
                REFERENCES workspace(id)
            """
        )
        op.execute(f"CREATE INDEX ix_{table}_workspace ON {table} (workspace_id)")


def downgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_workspace")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS workspace_id")
