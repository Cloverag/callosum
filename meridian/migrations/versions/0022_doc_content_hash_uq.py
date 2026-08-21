"""scope document content_hash deduplication per tenant workspace (Meridian P4)

In the initial frozen core schema (schema/postgres.sql), `document.content_hash` was
constrained by a global single-column UNIQUE constraint (`document_content_hash_key`).
For Meridian's multi-tenant architecture (Meridian P1/P4), identical content ingested
by distinct tenant organizations in their respective workspaces must be isolated and
permitted, while concurrent or duplicate uploads within the same workspace are rejected.

This migration replaces the global table constraint with a tenant-scoped composite
unique index on (workspace_id, content_hash).

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
            DROP CONSTRAINT IF EXISTS document_content_hash_key;

        CREATE UNIQUE INDEX IF NOT EXISTS uq_document_workspace_content_hash
            ON document (workspace_id, content_hash);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS uq_document_workspace_content_hash;

        ALTER TABLE document
            ADD CONSTRAINT document_content_hash_key UNIQUE (content_hash);
        """
    )
