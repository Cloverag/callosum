"""audit_event — immutable, append-only institutional audit trail (Meridian P2, checkpoint 8)

P2 owns the record; P8 owns execution. `audit_event` captures structured historical
action logs for all Meridian domain aggregate operations (meetings, decisions, board packs,
minutes, board members, resolutions, commitments).

Immutability invariant: `UPDATE` and `DELETE` privileges are explicitly revoked from
`callosum_app`. Once an audit row is written, it can never be altered or purged by the
runtime application role.

Revision ID: 0016_audit_event
Revises: 0015_commitment
Create Date: 2026-07-28
"""
from alembic import op

revision = "0016_audit_event"
down_revision = "0015_commitment"
branch_labels = None
depends_on = None

DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
_PREDICATE = "workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE audit_event (
            id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            workspace_id       UUID NOT NULL DEFAULT '{DEFAULT_WORKSPACE_ID}'::uuid
                               REFERENCES workspace(id) ON DELETE CASCADE,
            actor_principal_id UUID REFERENCES principal(id) ON DELETE RESTRICT,
            aggregate_type     TEXT NOT NULL,
            aggregate_id       UUID NOT NULL,
            action             TEXT NOT NULL,
            payload            JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        -- Performance indexes for tenant-scoped timeline queries
        CREATE INDEX idx_audit_event_workspace_aggregate
            ON audit_event (workspace_id, aggregate_type, aggregate_id, created_at DESC);

        CREATE INDEX idx_audit_event_workspace_actor
            ON audit_event (workspace_id, actor_principal_id, created_at DESC);

        -- Row-Level Security: Enable + Force
        ALTER TABLE audit_event ENABLE ROW LEVEL SECURITY;
        ALTER TABLE audit_event FORCE ROW LEVEL SECURITY;

        CREATE POLICY tenant_isolation ON audit_event
            FOR ALL
            USING ({_PREDICATE})
            WITH CHECK ({_PREDICATE});

        -- App role permissions: SELECT and INSERT only. UPDATE and DELETE are revoked.
        GRANT SELECT, INSERT ON audit_event TO callosum_app;
        REVOKE UPDATE, DELETE ON audit_event FROM callosum_app;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_event CASCADE;")
