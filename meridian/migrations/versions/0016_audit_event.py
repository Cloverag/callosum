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

# Constrained in SQL, not only in Python. `meridian/audit.py` validates these too, but
# that only protects callers who go through the module — and this table is append-only
# with UPDATE revoked, so a row written with a typo'd type can never be corrected AND is
# invisible to the query meant to find it. Same reasoning as the FR-EXEC-03 CHECK in
# `0015_commitment`: an invariant that matters belongs where it cannot be bypassed.
#
# Keep these in step with `AGGREGATE_TYPES` and `ACTIONS` in `meridian/audit.py`;
# `tests/test_audit.py` asserts the two agree, so a drift fails rather than rots.
_AGGREGATE_TYPES = (
    "('meeting', 'agenda_item', 'document', 'decision', 'board_pack', 'minutes', "
    "'board_member', 'resolution', 'commitment', 'audit')"
)
_ACTIONS = (
    "('created', 'updated', 'status_changed', 'superseded', 'published', 'deleted', "
    "'voted', 'reordered', 'item_added', 'item_removed', 'recorded')"
)


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE audit_event (
            id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

            -- RESTRICT, not CASCADE. Every domain table references workspace without a
            -- cascade; the only cascade in the schema is `membership` (0001), which is
            -- control plane. An audit log that a workspace deletion silently empties is
            -- the opposite of an audit log — it is precisely the record that should
            -- outlive the thing it describes. RESTRICT forces whoever writes the tenant
            -- offboarding path to make retention an explicit decision.
            workspace_id       UUID NOT NULL DEFAULT '{DEFAULT_WORKSPACE_ID}'::uuid
                               REFERENCES workspace(id) ON DELETE RESTRICT,

            -- Single-column, and it cannot be otherwise: `principal` has no
            -- `workspace_id` column — it is scoped through `membership` — so the
            -- composite (id, workspace_id) pattern used by 0012/0014/0015 has no target
            -- here. The FK therefore proves the principal EXISTS but not that they
            -- belong to this workspace, because Postgres validates foreign keys as the
            -- table owner and that bypasses RLS.
            --
            -- The workspace half is enforced in `record_audit_event()` by an RLS-scoped
            -- membership check, the same convention `add_pack_item` uses. Recorded here
            -- so the next reader does not assume this FK carries tenant isolation.
            actor_principal_id UUID REFERENCES principal(id) ON DELETE RESTRICT,

            aggregate_type     TEXT NOT NULL CHECK (aggregate_type IN {_AGGREGATE_TYPES}),
            aggregate_id       UUID NOT NULL,
            action             TEXT NOT NULL CHECK (action IN {_ACTIONS}),
            payload            JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
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
