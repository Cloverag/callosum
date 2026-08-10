"""principal_identity_multi_tenant — scope OIDC unique constraint to allow multi-workspace provisioning (Meridian P3, H-13)

Revision ID: 0018_identity_multi_tenant
Revises: 0017_principal_identity
Create Date: 2026-08-10 02:20:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0018_identity_multi_tenant"
down_revision = "0017_principal_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE principal_identity
        DROP CONSTRAINT principal_identity_provider_subject_uq,
        ADD CONSTRAINT principal_identity_provider_subject_principal_uq
            UNIQUE (provider, subject, principal_id);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE principal_identity
        DROP CONSTRAINT principal_identity_provider_subject_principal_uq,
        ADD CONSTRAINT principal_identity_provider_subject_uq
            UNIQUE (provider, subject);
        """
    )
