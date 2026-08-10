"""composite_tenant_foreign_keys — unbypassable tenant isolation at database schema level (Issue #41)

Revision ID: 0019_composite_tenant_foreign_keys
Revises: 0018_identity_multi_tenant
Create Date: 2026-08-10 03:58:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0019_composite_tenant_foreign_keys"
down_revision = "0018_identity_multi_tenant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        -- Step 1: Add UNIQUE (id, workspace_id) constraints on parent tables (if not already existing)
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'document_id_workspace_uq') THEN
                ALTER TABLE document ADD CONSTRAINT document_id_workspace_uq UNIQUE (id, workspace_id);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chunk_id_workspace_uq') THEN
                ALTER TABLE chunk ADD CONSTRAINT chunk_id_workspace_uq UNIQUE (id, workspace_id);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'meeting_id_workspace_uq') THEN
                ALTER TABLE meeting ADD CONSTRAINT meeting_id_workspace_uq UNIQUE (id, workspace_id);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'decision_id_workspace_uq') THEN
                ALTER TABLE decision ADD CONSTRAINT decision_id_workspace_uq UNIQUE (id, workspace_id);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'resolution_id_workspace_uq') THEN
                ALTER TABLE resolution ADD CONSTRAINT resolution_id_workspace_uq UNIQUE (id, workspace_id);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'commitment_id_workspace_uq') THEN
                ALTER TABLE commitment ADD CONSTRAINT commitment_id_workspace_uq UNIQUE (id, workspace_id);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'board_member_id_workspace_uq') THEN
                ALTER TABLE board_member ADD CONSTRAINT board_member_id_workspace_uq UNIQUE (id, workspace_id);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'board_pack_id_workspace_uq') THEN
                ALTER TABLE board_pack ADD CONSTRAINT board_pack_id_workspace_uq UNIQUE (id, workspace_id);
            END IF;
        END $$;

        -- Step 2: Add composite foreign keys (parent_id, workspace_id)
        ALTER TABLE chunk
            DROP CONSTRAINT IF EXISTS chunk_document_id_fkey,
            ADD CONSTRAINT chunk_document_workspace_fk
                FOREIGN KEY (document_id, workspace_id) REFERENCES document(id, workspace_id) ON DELETE CASCADE;

        ALTER TABLE agenda_item
            DROP CONSTRAINT IF EXISTS agenda_item_meeting_id_fkey,
            ADD CONSTRAINT agenda_item_meeting_workspace_fk
                FOREIGN KEY (meeting_id, workspace_id) REFERENCES meeting(id, workspace_id) ON DELETE CASCADE;

        ALTER TABLE decision
            DROP CONSTRAINT IF EXISTS decision_meeting_id_fkey,
            ADD CONSTRAINT decision_meeting_workspace_fk
                FOREIGN KEY (meeting_id, workspace_id) REFERENCES meeting(id, workspace_id) ON DELETE SET NULL;

        ALTER TABLE board_pack
            DROP CONSTRAINT IF EXISTS board_pack_meeting_id_fkey,
            ADD CONSTRAINT board_pack_meeting_workspace_fk
                FOREIGN KEY (meeting_id, workspace_id) REFERENCES meeting(id, workspace_id) ON DELETE CASCADE;

        ALTER TABLE board_pack_item
            DROP CONSTRAINT IF EXISTS board_pack_item_board_pack_id_fkey,
            ADD CONSTRAINT board_pack_item_pack_workspace_fk
                FOREIGN KEY (board_pack_id, workspace_id) REFERENCES board_pack(id, workspace_id) ON DELETE CASCADE;

        ALTER TABLE resolution
            DROP CONSTRAINT IF EXISTS resolution_decision_id_fkey,
            ADD CONSTRAINT resolution_decision_workspace_fk
                FOREIGN KEY (decision_id, workspace_id) REFERENCES decision(id, workspace_id);

        ALTER TABLE resolution_vote
            DROP CONSTRAINT IF EXISTS resolution_vote_resolution_id_fkey,
            DROP CONSTRAINT IF EXISTS resolution_vote_board_member_id_fkey,
            ADD CONSTRAINT resolution_vote_resolution_workspace_fk
                FOREIGN KEY (resolution_id, workspace_id) REFERENCES resolution(id, workspace_id) ON DELETE CASCADE,
            ADD CONSTRAINT resolution_vote_member_workspace_fk
                FOREIGN KEY (board_member_id, workspace_id) REFERENCES board_member(id, workspace_id);

        ALTER TABLE commitment
            DROP CONSTRAINT IF EXISTS commitment_decision_id_fkey,
            DROP CONSTRAINT IF EXISTS commitment_resolution_id_fkey,
            DROP CONSTRAINT IF EXISTS commitment_owner_board_member_id_fkey,
            ADD CONSTRAINT commitment_decision_workspace_fk
                FOREIGN KEY (decision_id, workspace_id) REFERENCES decision(id, workspace_id),
            ADD CONSTRAINT commitment_resolution_workspace_fk
                FOREIGN KEY (resolution_id, workspace_id) REFERENCES resolution(id, workspace_id),
            ADD CONSTRAINT commitment_owner_workspace_fk
                FOREIGN KEY (owner_board_member_id, workspace_id) REFERENCES board_member(id, workspace_id);

        ALTER TABLE commitment_update
            DROP CONSTRAINT IF EXISTS commitment_update_commitment_id_fkey,
            ADD CONSTRAINT commitment_update_commitment_workspace_fk
                FOREIGN KEY (commitment_id, workspace_id) REFERENCES commitment(id, workspace_id) ON DELETE CASCADE;

        ALTER TABLE proposed_change
            DROP CONSTRAINT IF EXISTS proposed_change_document_id_fkey,
            DROP CONSTRAINT IF EXISTS proposed_change_chunk_id_fkey,
            ADD CONSTRAINT proposed_change_document_workspace_fk
                FOREIGN KEY (document_id, workspace_id) REFERENCES document(id, workspace_id) ON DELETE CASCADE,
            ADD CONSTRAINT proposed_change_chunk_workspace_fk
                FOREIGN KEY (chunk_id, workspace_id) REFERENCES chunk(id, workspace_id) ON DELETE CASCADE;

        ALTER TABLE extraction_failure
            DROP CONSTRAINT IF EXISTS extraction_failure_document_id_fkey,
            DROP CONSTRAINT IF EXISTS extraction_failure_chunk_id_fkey,
            ADD CONSTRAINT extraction_failure_document_workspace_fk
                FOREIGN KEY (document_id, workspace_id) REFERENCES document(id, workspace_id) ON DELETE CASCADE,
            ADD CONSTRAINT extraction_failure_chunk_workspace_fk
                FOREIGN KEY (chunk_id, workspace_id) REFERENCES chunk(id, workspace_id) ON DELETE CASCADE;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE chunk DROP CONSTRAINT IF EXISTS chunk_document_workspace_fk;
        ALTER TABLE agenda_item DROP CONSTRAINT IF EXISTS agenda_item_meeting_workspace_fk;
        ALTER TABLE decision DROP CONSTRAINT IF EXISTS decision_meeting_workspace_fk;
        ALTER TABLE board_pack DROP CONSTRAINT IF EXISTS board_pack_meeting_workspace_fk;
        ALTER TABLE board_pack_item DROP CONSTRAINT IF EXISTS board_pack_item_pack_workspace_fk;
        ALTER TABLE resolution DROP CONSTRAINT IF EXISTS resolution_decision_workspace_fk;
        ALTER TABLE resolution_vote DROP CONSTRAINT IF EXISTS resolution_vote_resolution_workspace_fk;
        ALTER TABLE resolution_vote DROP CONSTRAINT IF EXISTS resolution_vote_member_workspace_fk;
        ALTER TABLE commitment DROP CONSTRAINT IF EXISTS commitment_decision_workspace_fk;
        ALTER TABLE commitment DROP CONSTRAINT IF EXISTS commitment_resolution_workspace_fk;
        ALTER TABLE commitment DROP CONSTRAINT IF EXISTS commitment_owner_workspace_fk;
        ALTER TABLE commitment_update DROP CONSTRAINT IF EXISTS commitment_update_commitment_workspace_fk;
        ALTER TABLE proposed_change DROP CONSTRAINT IF EXISTS proposed_change_document_workspace_fk;
        ALTER TABLE proposed_change DROP CONSTRAINT IF EXISTS proposed_change_chunk_workspace_fk;
        ALTER TABLE extraction_failure DROP CONSTRAINT IF EXISTS extraction_failure_document_workspace_fk;
        ALTER TABLE extraction_failure DROP CONSTRAINT IF EXISTS extraction_failure_chunk_workspace_fk;

        ALTER TABLE document DROP CONSTRAINT IF EXISTS document_id_workspace_uq;
        ALTER TABLE chunk DROP CONSTRAINT IF EXISTS chunk_id_workspace_uq;
        ALTER TABLE meeting DROP CONSTRAINT IF EXISTS meeting_id_workspace_uq;
        ALTER TABLE decision DROP CONSTRAINT IF EXISTS decision_id_workspace_uq;
        ALTER TABLE resolution DROP CONSTRAINT IF EXISTS resolution_id_workspace_uq;
        ALTER TABLE commitment DROP CONSTRAINT IF EXISTS commitment_id_workspace_uq;
        ALTER TABLE board_member DROP CONSTRAINT IF EXISTS board_member_id_workspace_uq;
        ALTER TABLE board_pack DROP CONSTRAINT IF EXISTS board_pack_id_workspace_uq;
        """
    )
