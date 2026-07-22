"""agenda_item — product-domain aggregate (Meridian P2, checkpoint 2)

Adds the agenda_item table attached to meeting(id) ON DELETE CASCADE.
Carries workspace_id + fail-closed RLS matching migrations 0003/0005/0007.

`position` is a 1-indexed contiguous integer per meeting. Uniqueness is deferred
(`INITIALLY DEFERRED`) so atomic reordering (1 ↔ 2 swaps or full list re-keying)
can execute in a single SQL transaction without intermediate uniqueness collisions.

`version` is an optimistic-concurrency counter starting at 1; every mutation bumps it.

Revision ID: 0008_agenda_item
Revises: 0007_meeting
Create Date: 2026-07-22
"""
from alembic import op

revision = "0008_agenda_item"
down_revision = "0007_meeting"
branch_labels = None
depends_on = None

DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
_PREDICATE = "workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE agenda_item (
            id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            meeting_id        UUID NOT NULL REFERENCES meeting(id) ON DELETE CASCADE,
            title             TEXT NOT NULL,
            description       TEXT,
            duration_minutes  INT,
            presenter         TEXT,
            position          INT NOT NULL,
            version           INT NOT NULL DEFAULT 1,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            workspace_id      UUID NOT NULL DEFAULT '{DEFAULT_WORKSPACE_ID}' REFERENCES workspace(id),

            CONSTRAINT agenda_title_not_empty CHECK (length(trim(title)) > 0),
            CONSTRAINT agenda_position_positive CHECK (position > 0),
            CONSTRAINT agenda_duration_positive CHECK (duration_minutes IS NULL OR duration_minutes > 0),
            CONSTRAINT agenda_unique_position UNIQUE (meeting_id, position) INITIALLY DEFERRED
        )
        """
    )
    op.execute("CREATE INDEX ix_agenda_item_meeting ON agenda_item (meeting_id, position)")
    op.execute("CREATE INDEX ix_agenda_item_workspace ON agenda_item (workspace_id)")

    op.execute("ALTER TABLE agenda_item ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agenda_item FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON agenda_item
            FOR ALL
            USING ({_PREDICATE})
            WITH CHECK ({_PREDICATE})
        """
    )

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON agenda_item TO callosum_app")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON agenda_item")
    op.execute("DROP TABLE IF EXISTS agenda_item")
