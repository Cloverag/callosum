"""add unique constraint on document(workspace_id, content_hash) (Meridian P4)

Prevents duplicate ingestions of identical document content within the same
tenant workspace at the database level, eliminating the race condition on
concurrent uploads.

Revision ID: 0022_doc_content_hash_uq
Revises: 0021_fix_composite_fk_cascades
Create Date: 2026-08-13
"""
from alembic import op

revision = "0022_doc_content_hash_uq"
down_revision = "0021_fix_composite_fk_cascades"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE document
            ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

        CREATE UNIQUE INDEX IF NOT EXISTS uq_document_workspace_content_hash
            ON document (workspace_id, content_hash);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS uq_document_workspace_content_hash;
        ALTER TABLE document
            DROP COLUMN IF EXISTS updated_at,
            DROP COLUMN IF EXISTS created_at;
        """
    )
