"""fix_composite_fk_cascade_semantics — restore intended ON DELETE CASCADE/SET NULL semantics on composite tenant FKs (Issue #122)

Revision ID: 0021_fix_composite_fk_cascade_semantics
Revises: 0020_meeting_importance
Create Date: 2026-08-13 05:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0021_fix_composite_fk_cascade_semantics"
down_revision = "0020_meeting_importance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        -- 1. Restore ON DELETE CASCADE on decision -> meeting (was ON DELETE SET NULL in 0019, causing NOT NULL violation)
        ALTER TABLE decision
            DROP CONSTRAINT IF EXISTS decision_meeting_workspace_fk,
            ADD CONSTRAINT decision_meeting_workspace_fk
                FOREIGN KEY (meeting_id, workspace_id) REFERENCES meeting(id, workspace_id) ON DELETE CASCADE;

        -- 2. Restore ON DELETE CASCADE on resolution -> decision
        ALTER TABLE resolution
            DROP CONSTRAINT IF EXISTS resolution_decision_workspace_fk,
            ADD CONSTRAINT resolution_decision_workspace_fk
                FOREIGN KEY (decision_id, workspace_id) REFERENCES decision(id, workspace_id) ON DELETE CASCADE;

        -- 3. Restore ON DELETE CASCADE on resolution_vote -> resolution and board_member
        ALTER TABLE resolution_vote
            DROP CONSTRAINT IF EXISTS resolution_vote_resolution_workspace_fk,
            DROP CONSTRAINT IF EXISTS resolution_vote_member_workspace_fk,
            ADD CONSTRAINT resolution_vote_resolution_workspace_fk
                FOREIGN KEY (resolution_id, workspace_id) REFERENCES resolution(id, workspace_id) ON DELETE CASCADE,
            ADD CONSTRAINT resolution_vote_member_workspace_fk
                FOREIGN KEY (board_member_id, workspace_id) REFERENCES board_member(id, workspace_id) ON DELETE CASCADE;

        -- 4. Restore ON DELETE CASCADE / SET NULL on commitment
        ALTER TABLE commitment
            DROP CONSTRAINT IF EXISTS commitment_decision_workspace_fk,
            DROP CONSTRAINT IF EXISTS commitment_resolution_workspace_fk,
            DROP CONSTRAINT IF EXISTS commitment_owner_workspace_fk,
            ADD CONSTRAINT commitment_decision_workspace_fk
                FOREIGN KEY (decision_id, workspace_id) REFERENCES decision(id, workspace_id) ON DELETE CASCADE,
            ADD CONSTRAINT commitment_resolution_workspace_fk
                FOREIGN KEY (resolution_id, workspace_id) REFERENCES resolution(id, workspace_id) ON DELETE SET NULL,
            ADD CONSTRAINT commitment_owner_workspace_fk
                FOREIGN KEY (owner_board_member_id, workspace_id) REFERENCES board_member(id, workspace_id) ON DELETE CASCADE;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE decision
            DROP CONSTRAINT IF EXISTS decision_meeting_workspace_fk,
            ADD CONSTRAINT decision_meeting_workspace_fk
                FOREIGN KEY (meeting_id, workspace_id) REFERENCES meeting(id, workspace_id) ON DELETE SET NULL;

        ALTER TABLE resolution
            DROP CONSTRAINT IF EXISTS resolution_decision_workspace_fk,
            ADD CONSTRAINT resolution_decision_workspace_fk
                FOREIGN KEY (decision_id, workspace_id) REFERENCES decision(id, workspace_id);

        ALTER TABLE resolution_vote
            DROP CONSTRAINT IF EXISTS resolution_vote_resolution_workspace_fk,
            DROP CONSTRAINT IF EXISTS resolution_vote_member_workspace_fk,
            ADD CONSTRAINT resolution_vote_resolution_workspace_fk
                FOREIGN KEY (resolution_id, workspace_id) REFERENCES resolution(id, workspace_id) ON DELETE CASCADE,
            ADD CONSTRAINT resolution_vote_member_workspace_fk
                FOREIGN KEY (board_member_id, workspace_id) REFERENCES board_member(id, workspace_id);

        ALTER TABLE commitment
            DROP CONSTRAINT IF EXISTS commitment_decision_workspace_fk,
            DROP CONSTRAINT IF EXISTS commitment_resolution_workspace_fk,
            DROP CONSTRAINT IF EXISTS commitment_owner_workspace_fk,
            ADD CONSTRAINT commitment_decision_workspace_fk
                FOREIGN KEY (decision_id, workspace_id) REFERENCES decision(id, workspace_id),
            ADD CONSTRAINT commitment_resolution_workspace_fk
                FOREIGN KEY (resolution_id, workspace_id) REFERENCES resolution(id, workspace_id),
            ADD CONSTRAINT commitment_owner_workspace_fk
                FOREIGN KEY (owner_board_member_id, workspace_id) REFERENCES board_member(id, workspace_id);
        """
    )
