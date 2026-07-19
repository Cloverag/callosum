"""workspace + membership — tenancy foundation (Meridian P1, brick 1)

Creates the two objects that make multi-tenancy possible, WITHOUT yet touching any
existing (frozen-era) table:

  * workspace   — one row per customer company ("an apartment")
  * membership  — which principal belongs to which workspace, and at what clearance
                  (clearance is per-workspace: a founder in their own workspace may be
                  only an observer in another)

It also inserts one Default Workspace so that, in the next brick, existing
single-tenant data has a workspace to be assigned to.

Revision ID: 0001_workspace_membership
Revises:
Create Date: 2026-07-18
"""
from alembic import op

revision = "0001_workspace_membership"
down_revision = None
branch_labels = None
depends_on = None

# Stable, well-known id so later migrations and backfills can reference it.
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    op.execute(
        """
        CREATE TABLE workspace (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name        TEXT NOT NULL,
            external_id TEXT UNIQUE,          -- maps to the auth provider's org id (Kinde org)
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE membership (
            principal_id UUID NOT NULL REFERENCES principal(id)     ON DELETE CASCADE,
            workspace_id UUID NOT NULL REFERENCES workspace(id)     ON DELETE CASCADE,
            role         TEXT NOT NULL,        -- founder | admin | exec | director | observer | advisor
            clearance    INT  NOT NULL REFERENCES sensitivity(level),
            active       BOOLEAN NOT NULL DEFAULT true,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (principal_id, workspace_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_membership_workspace ON membership (workspace_id)")

    op.execute(
        f"""
        INSERT INTO workspace (id, name, external_id)
        VALUES ('{DEFAULT_WORKSPACE_ID}', 'Default Workspace', 'default')
        ON CONFLICT (external_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS membership")
    op.execute("DROP TABLE IF EXISTS workspace")
