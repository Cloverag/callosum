"""board_pack, board_pack_item, and minutes — product-domain aggregate (Meridian P2, checkpoint 3)

Adds board_pack, board_pack_item, and minutes tables attached to meeting(id).
Carries workspace_id + fail-closed RLS matching migrations 0003/0005/0007/0008/0009.

`version` is an optimistic-concurrency counter starting at 1; every mutation bumps it.

Revision ID: 0010_board_pack
Revises: 0009_decision
Create Date: 2026-07-26
"""
from alembic import op

revision = "0010_board_pack"
down_revision = "0009_decision"
branch_labels = None
depends_on = None

DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
_PREDICATE = "workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid"
_PACK_STATUSES = "('draft', 'published', 'archived')"
_MINUTES_STATUSES = "('draft', 'final')"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE board_pack (
            id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            meeting_id        UUID NOT NULL REFERENCES meeting(id) ON DELETE CASCADE,
            title             TEXT NOT NULL,
            status            TEXT NOT NULL DEFAULT 'draft' CHECK (status IN {_PACK_STATUSES}),
            version_no        INT NOT NULL DEFAULT 1,
            superseded_by_id  UUID REFERENCES board_pack(id) ON DELETE SET NULL,
            published_at      TIMESTAMPTZ,
            version           INT NOT NULL DEFAULT 1,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            workspace_id      UUID NOT NULL DEFAULT '{DEFAULT_WORKSPACE_ID}' REFERENCES workspace(id),

            CONSTRAINT pack_title_not_empty CHECK (length(trim(title)) > 0)
        )
        """
    )
    op.execute("CREATE INDEX ix_board_pack_meeting ON board_pack (meeting_id)")
    op.execute("CREATE INDEX ix_board_pack_workspace ON board_pack (workspace_id)")
    op.execute("CREATE INDEX ix_board_pack_status ON board_pack (status)")

    op.execute(
        f"""
        CREATE TABLE board_pack_item (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            board_pack_id   UUID NOT NULL REFERENCES board_pack(id) ON DELETE CASCADE,
            document_id     UUID NOT NULL REFERENCES document(id) ON DELETE RESTRICT,
            agenda_item_id  UUID REFERENCES agenda_item(id) ON DELETE SET NULL,
            position        INT NOT NULL,
            note            TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            workspace_id    UUID NOT NULL DEFAULT '{DEFAULT_WORKSPACE_ID}' REFERENCES workspace(id),

            CONSTRAINT pack_item_position_positive CHECK (position > 0),
            CONSTRAINT pack_item_unique_document UNIQUE (board_pack_id, document_id),
            CONSTRAINT pack_item_unique_position UNIQUE (board_pack_id, position) DEFERRABLE INITIALLY DEFERRED
        )
        """
    )
    op.execute("CREATE INDEX ix_board_pack_item_pack ON board_pack_item (board_pack_id, position)")
    op.execute("CREATE INDEX ix_board_pack_item_doc ON board_pack_item (document_id)")

    op.execute(
        f"""
        CREATE TABLE minutes (
            id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            meeting_id        UUID NOT NULL REFERENCES meeting(id) ON DELETE CASCADE,
            body              TEXT NOT NULL,
            status            TEXT NOT NULL DEFAULT 'draft' CHECK (status IN {_MINUTES_STATUSES}),
            version_no        INT NOT NULL DEFAULT 1,
            superseded_by_id  UUID REFERENCES minutes(id) ON DELETE SET NULL,
            finalised_at      TIMESTAMPTZ,
            version           INT NOT NULL DEFAULT 1,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            workspace_id      UUID NOT NULL DEFAULT '{DEFAULT_WORKSPACE_ID}' REFERENCES workspace(id),

            CONSTRAINT minutes_body_not_empty CHECK (length(trim(body)) > 0)
        )
        """
    )
    op.execute("CREATE INDEX ix_minutes_meeting ON minutes (meeting_id)")
    op.execute("CREATE INDEX ix_minutes_workspace ON minutes (workspace_id)")

    for tbl in ("board_pack", "board_pack_item", "minutes"):
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {tbl}
                FOR ALL
                USING ({_PREDICATE})
                WITH CHECK ({_PREDICATE})
            """
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {tbl} TO callosum_app")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON minutes")
    op.execute("DROP TABLE IF EXISTS minutes")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON board_pack_item")
    op.execute("DROP TABLE IF EXISTS board_pack_item")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON board_pack")
    op.execute("DROP TABLE IF EXISTS board_pack")
