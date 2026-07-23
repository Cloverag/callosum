"""decision & decision_stance — product-domain aggregate (Meridian P2, checkpoint 4)

Adds the decision and decision_stance tables attached to meeting(id) and agenda_item(id).
Carries workspace_id + fail-closed RLS matching migrations 0003/0005/0007/0008.

`version` is an optimistic-concurrency counter starting at 1; every mutation bumps it.

Revision ID: 0009_decision
Revises: 0008_agenda_item
Create Date: 2026-07-23
"""
from alembic import op

revision = "0009_decision"
down_revision = "0008_agenda_item"
branch_labels = None
depends_on = None

DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
_PREDICATE = "workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid"
_STATUSES = "('proposed', 'approved', 'rejected', 'superseded', 'deferred')"
_STANCES = "('SUPPORTED', 'OPPOSED', 'APPROVED', 'REQUESTED')"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE decision (
            id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            meeting_id        UUID NOT NULL REFERENCES meeting(id) ON DELETE CASCADE,
            agenda_item_id    UUID REFERENCES agenda_item(id) ON DELETE SET NULL,
            title             TEXT NOT NULL,
            rationale         TEXT,
            status            TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN {_STATUSES}),
            superseded_by_id  UUID REFERENCES decision(id) ON DELETE SET NULL,
            version           INT NOT NULL DEFAULT 1,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            workspace_id      UUID NOT NULL DEFAULT '{DEFAULT_WORKSPACE_ID}' REFERENCES workspace(id),

            CONSTRAINT decision_title_not_empty CHECK (length(trim(title)) > 0)
        )
        """
    )
    op.execute("CREATE INDEX ix_decision_meeting ON decision (meeting_id)")
    op.execute("CREATE INDEX ix_decision_workspace ON decision (workspace_id)")
    op.execute("CREATE INDEX ix_decision_status ON decision (status)")

    op.execute(
        f"""
        CREATE TABLE decision_stance (
            id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            decision_id   UUID NOT NULL REFERENCES decision(id) ON DELETE CASCADE,
            person_name   TEXT NOT NULL,
            stance        TEXT NOT NULL CHECK (stance IN {_STANCES}),
            comment       TEXT,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            workspace_id  UUID NOT NULL DEFAULT '{DEFAULT_WORKSPACE_ID}' REFERENCES workspace(id),

            CONSTRAINT stance_person_not_empty CHECK (length(trim(person_name)) > 0),
            CONSTRAINT stance_unique_person UNIQUE (decision_id, person_name)
        )
        """
    )
    op.execute("CREATE INDEX ix_decision_stance_decision ON decision_stance (decision_id)")

    for tbl in ("decision", "decision_stance"):
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
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON decision_stance")
    op.execute("DROP TABLE IF EXISTS decision_stance")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON decision")
    op.execute("DROP TABLE IF EXISTS decision")
