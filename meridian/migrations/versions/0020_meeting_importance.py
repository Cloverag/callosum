"""meeting_importance — domain importance classification field (Meridian P6, Issue #108)

Revision ID: 0020_meeting_importance
Revises: 0019_composite_tenant_fks
Create Date: 2026-08-10 04:30:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0020_meeting_importance"
down_revision = "0019_composite_tenant_fks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE meeting
            ADD COLUMN importance TEXT NOT NULL DEFAULT 'routine',
            ADD CONSTRAINT meeting_importance_check
                CHECK (importance IN ('critical', 'high', 'routine', 'low'));
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE meeting
            DROP CONSTRAINT IF EXISTS meeting_importance_check,
            DROP COLUMN IF EXISTS importance;
        """
    )
