"""meeting — product-domain aggregate root (Meridian P2, checkpoint 1)

The first product-forward object since P1. The board meeting is the aggregate root:
agenda items, board packs, minutes, decisions and action items all hang off a meeting
in later checkpoints. This migration adds ONLY the meeting table — the root is
stabilised on its own before anything is attached to it.

meeting is a tenant-owned table, so it carries workspace_id + fail-closed RLS from
creation, consistent with migrations 0002/0003/0005. The workspace_id DEFAULT keeps
default-workspace inserts working; product code sets it explicitly.

Lifecycle — the allowed SET is guarded here by a CHECK; the transition RULES
(draft -> scheduled -> in_progress -> completed, and any non-terminal -> cancelled,
with completed/cancelled terminal) live in meridian/meetings.py with negative tests.

`version` is an optimistic-concurrency counter: it starts at 1 and every mutation
bumps it, so update/transition can detect a lost update without holding row locks.

Revision ID: 0007_meeting
Revises: 0006_conflict_workspace_uq
Create Date: 2026-07-21
"""
from alembic import op

revision = "0007_meeting"
down_revision = "0006_conflict_workspace_uq"
branch_labels = None
depends_on = None

DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
_PREDICATE = "workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid"
_STATUSES = "('draft', 'scheduled', 'in_progress', 'completed', 'cancelled')"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE meeting (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            title           TEXT NOT NULL,
            scheduled_start TIMESTAMPTZ,
            scheduled_end   TIMESTAMPTZ,
            location        TEXT,
            status          TEXT NOT NULL DEFAULT 'draft' CHECK (status IN {_STATUSES}),
            version         INT  NOT NULL DEFAULT 1,
            created_by      UUID REFERENCES principal(id),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            workspace_id    UUID NOT NULL DEFAULT '{DEFAULT_WORKSPACE_ID}' REFERENCES workspace(id)
        )
        """
    )
    op.execute("CREATE INDEX ix_meeting_workspace ON meeting (workspace_id)")
    op.execute("CREATE INDEX ix_meeting_status ON meeting (status)")
    op.execute("CREATE INDEX ix_meeting_scheduled_start ON meeting (scheduled_start)")

    # Same fail-closed tenant lock as the other tenant tables (migrations 0003/0005).
    op.execute("ALTER TABLE meeting ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE meeting FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON meeting
            FOR ALL
            USING ({_PREDICATE})
            WITH CHECK ({_PREDICATE})
        """
    )

    # Explicit runtime grant (0004's default privileges already cover this).
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON meeting TO callosum_app")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON meeting")
    op.execute("DROP TABLE IF EXISTS meeting")
