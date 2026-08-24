"""document_version — a document is corrected by supersession, never by mutation (Meridian P4)

`document` is the one governed object in this product that could not be revised.
`decision`, `board_pack` and `minutes` all carry `superseded_by_id` and a `supersede_*`
function; `document` — the object the entire graph is derived from — carried neither.

The practical consequence: intake is content-addressed and tenant-scoped
(`uq_document_workspace_content_hash`, `0022`), so re-filing *corrected* text is not a
duplicate. It is a second, unrelated document. The workspace then holds two documents
that disagree, nothing records that one replaces the other, and a reader has no way to
tell which is current.

`schema/postgres.sql` is FROZEN (CONTRIBUTING.md) and is deliberately not edited. Altering
`document` through a migration is the established practice on this table: `0019` added
`document_id_workspace_uq`, `0022` replaced its content-hash constraint. Both left the
frozen file alone.

Slot moved 0023 -> 0024 on 2026-08-23. PR #153 claimed `0023` first with the same parent
(`0022_doc_content_hash_uq`), and two revisions sharing a parent give Alembic two heads —
`alembic upgrade head` then fails outright rather than picking one. This one moved because
#153 was opened first and the backend is its author's under `rules.md` §5, not because
either change depends on the other: they are independent, and the order between them is
arbitrary.

Revision ID: 0024_document_version
Revises: 0023_audit_intake_refused
Create Date: 2026-08-23

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0024_document_version"
down_revision = "0023_audit_intake_refused"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE document
            ADD COLUMN superseded_by_id UUID,
            ADD COLUMN revision INT NOT NULL DEFAULT 1;

        ALTER TABLE document
            ADD CONSTRAINT document_revision_check
                CHECK (revision >= 1);

        -- A document cannot replace itself. Cheap, and it makes the one-step cycle
        -- unrepresentable rather than merely unreachable from today's call sites.
        ALTER TABLE document
            ADD CONSTRAINT document_no_self_supersede
                CHECK (superseded_by_id IS NULL OR superseded_by_id <> id);

        -- COMPOSITE, against `document_id_workspace_uq` which 0019 already created.
        -- A single-column self-FK would let one workspace's document name another
        -- workspace's as its successor -- precisely the defect class (D-001) that
        -- 0019 exists to close, reintroduced on a new column.
        --
        -- `ON DELETE SET NULL (superseded_by_id)` rather than a bare SET NULL: the FK
        -- spans `workspace_id`, which is NOT NULL, so the unqualified form would try to
        -- null it and fail. The column-list form is PostgreSQL 15+; the image is
        -- pgvector/pgvector:pg16.
        --
        -- NO ACTION was the alternative and is rejected on a MEASURED difference, not a
        -- guessed one. Deleting a document that some earlier revision points at is
        -- refused outright under NO ACTION, which makes the predecessor uncollectable:
        -- the only way to remove the successor is to find and unlink every document
        -- naming it first. Verified on 16.14 -- deleting the successor under this clause
        -- nulls `superseded_by_id` and leaves `workspace_id` intact.
        --
        -- A first draft of this comment justified the choice by claiming NO ACTION would
        -- break workspace deletion. That is FALSE and is recorded here rather than
        -- quietly dropped: `document_workspace_id_fkey` carries no ON DELETE clause at
        -- all, so a workspace delete already fails while any document exists -- on
        -- master, with or without this migration. The plausible reason was not the real
        -- one, which is the failure mode 0021 was actually about.
        ALTER TABLE document
            ADD CONSTRAINT document_superseded_by_workspace_fk
                FOREIGN KEY (superseded_by_id, workspace_id)
                REFERENCES document(id, workspace_id)
                ON DELETE SET NULL (superseded_by_id);

        -- What makes the chain a CHAIN. Without it two documents may both name the same
        -- successor, and a reader walking backwards from the head finds a fork with no
        -- way to say which predecessor is the real one. One predecessor per revision,
        -- enforced in the database rather than by convention in the domain.
        CREATE UNIQUE INDEX uq_document_superseded_by
            ON document (workspace_id, superseded_by_id)
         WHERE superseded_by_id IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS uq_document_superseded_by;

        ALTER TABLE document
            DROP CONSTRAINT IF EXISTS document_superseded_by_workspace_fk,
            DROP CONSTRAINT IF EXISTS document_no_self_supersede,
            DROP CONSTRAINT IF EXISTS document_revision_check,
            DROP COLUMN IF EXISTS revision,
            DROP COLUMN IF EXISTS superseded_by_id;
        """
    )
