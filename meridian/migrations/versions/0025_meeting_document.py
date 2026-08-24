"""meeting_document — source material assigned to a meeting (Meridian P4)

The last unbuilt P4 work item: "Workspace / meeting assignment" (phase.md, ROADMAP.md).

Today a document and a meeting can only be related through a **board pack**. That is a
published, ordered, versioned artifact with its own lifecycle, and it is P5's object.
Gathering material is the step *before* one exists: someone says "this contract is for
the March board" days before anyone assembles the pack, and there is nowhere to record
it. The material lives in a chat thread, and the pack is assembled from memory.

So this table is deliberately NOT a second board_pack_item. It carries no `position`, no
`note`, no ordering and no publication state, because it makes no claim about the agenda.
It records one fact — this document is material for this meeting — and who said so.

WHY THE FKs ARE COMPOSITE
-------------------------
`(meeting_id, workspace_id)` and `(document_id, workspace_id)`, against the
`meeting_id_workspace_uq` and `document_id_workspace_uq` constraints `0019` added.

A single-column FK would let one workspace's meeting claim another workspace's document.
RLS scopes what a *session* can read, but a foreign key is checked by the system, not by
the session — the reference itself would be created successfully and only fail to resolve
at read time. That is the exact defect class `0019` exists to close, and `0021` had to
repair once already where the cascade behaviour was wrong.

ON DELETE CASCADE on both sides. This row is an assertion *about* a pair; with either
half deleted it asserts nothing, and there is no orphan state worth preserving. Contrast
`0024`'s `superseded_by_id`, which is SET NULL because the surviving document is still a
document with its own history.

WHAT THE UNIQUE INDEX DOES
--------------------------
`(workspace_id, meeting_id, document_id)` — assigning the same document twice is not a
second fact, and without the constraint the domain would have to read-then-write to find
out, which races. The database answers it.

`schema/postgres.sql` is FROZEN (CONTRIBUTING.md) and is not edited; a new product table
arrives by migration, as `0012`, `0014`, `0015` and `0016` all did.

Revision ID: 0025_meeting_document
Revises: 0024_document_version
Create Date: 2026-08-24

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0025_meeting_document"
down_revision = "0024_document_version"
branch_labels = None
depends_on = None

_PREDICATE = "workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE meeting_document (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            workspace_id    UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001'
                                REFERENCES workspace(id),
            meeting_id      UUID NOT NULL,
            document_id     UUID NOT NULL,

            -- Who assigned it. Nullable for the same reason `document.authored_by` is:
            -- material can arrive through a path with no board member attached, and a
            -- fabricated attribution is worse than an absent one.
            assigned_by     UUID,
            assigned_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT meeting_document_meeting_fk
                FOREIGN KEY (meeting_id, workspace_id)
                REFERENCES meeting (id, workspace_id)
                ON DELETE CASCADE,

            CONSTRAINT meeting_document_document_fk
                FOREIGN KEY (document_id, workspace_id)
                REFERENCES document (id, workspace_id)
                ON DELETE CASCADE
        )
        """
    )

    # One assignment per pair. Assigning twice is not a second fact, and the constraint
    # means the domain can attempt the insert instead of reading first and racing.
    op.execute(
        "CREATE UNIQUE INDEX uq_meeting_document "
        "ON meeting_document (workspace_id, meeting_id, document_id)"
    )
    # The read path is "material for this meeting", so the index leads with the meeting.
    op.execute(
        "CREATE INDEX ix_meeting_document_meeting "
        "ON meeting_document (workspace_id, meeting_id)"
    )
    # And the reverse — "which meetings is this document material for" — is the document
    # detail view, which would otherwise scan.
    op.execute(
        "CREATE INDEX ix_meeting_document_document "
        "ON meeting_document (workspace_id, document_id)"
    )

    op.execute("ALTER TABLE meeting_document ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE meeting_document FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON meeting_document
            FOR ALL
            USING ({_PREDICATE})
            WITH CHECK ({_PREDICATE})
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON meeting_document TO callosum_app")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON meeting_document")
    op.execute("DROP TABLE IF EXISTS meeting_document")
