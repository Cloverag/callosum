"""entity_conflict review queue — tenant-scoped (Devguru PR #6, integrated onto P1 chain)

Human-in-the-loop entity-conflict / ALIAS_OF review queue. Detection is a deterministic
rapidfuzz scan; approval routes through proposed_change -> store.approve(), the only path
that writes to Neo4j, so provenance invariants hold.

Integration notes (Meridian P1):
  * Re-parented onto the tenancy chain (down_revision = 0004_app_role) so there is a single
    linear Alembic history — the original PR #6 migration was authored off master before the
    tenancy migrations existed and was a second root.
  * entity_conflict is a tenant-owned table, so it carries workspace_id + RLS from creation,
    consistent with migrations 0002/0003. The DEFAULT keeps single-tenant inserts working and
    should be DROPPED once product code sets workspace_id explicitly.
  * callosum_app already auto-receives DML here via 0004's ALTER DEFAULT PRIVILEGES; the
    explicit GRANT below makes that intent obvious and independent of ordering.

Revision ID: 0005_entity_conflict
Revises: 0004_app_role
Create Date: 2026-07-19
"""
from alembic import op

revision = "0005_entity_conflict"
down_revision = "0004_app_role"
branch_labels = None
depends_on = None

DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
_PREDICATE = "workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE entity_conflict (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name_a          TEXT NOT NULL,
            type_a          TEXT NOT NULL,
            name_b          TEXT NOT NULL,
            type_b          TEXT NOT NULL,
            similarity      REAL NOT NULL,
            chunk_id_a      UUID REFERENCES chunk(id) ON DELETE SET NULL,
            chunk_id_b      UUID REFERENCES chunk(id) ON DELETE SET NULL,
            quote_a         TEXT,
            quote_b         TEXT,
            sensitivity     INT NOT NULL DEFAULT 1 REFERENCES sensitivity(level),
            status          TEXT NOT NULL DEFAULT 'pending',
            reviewed_by     UUID REFERENCES principal(id),
            reviewed_at     TIMESTAMPTZ,
            change_id       UUID REFERENCES proposed_change(id),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            workspace_id    UUID NOT NULL DEFAULT '{DEFAULT_WORKSPACE_ID}' REFERENCES workspace(id),
            UNIQUE (name_a, type_a, name_b, type_b)
        )
        """
    )
    op.execute("CREATE INDEX entity_conflict_status_idx ON entity_conflict (status)")
    op.execute("CREATE INDEX entity_conflict_sensitivity_idx ON entity_conflict (sensitivity)")
    op.execute("CREATE INDEX ix_entity_conflict_workspace ON entity_conflict (workspace_id)")

    # Same fail-closed tenant lock as the other tenant tables (migration 0003).
    op.execute("ALTER TABLE entity_conflict ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE entity_conflict FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON entity_conflict
            FOR ALL
            USING ({_PREDICATE})
            WITH CHECK ({_PREDICATE})
        """
    )

    # Explicit runtime grant (0004's default privileges already cover this).
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON entity_conflict TO callosum_app"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON entity_conflict")
    op.execute("DROP TABLE IF EXISTS entity_conflict")
