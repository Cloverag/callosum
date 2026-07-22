"""entity_conflict UNIQUE key: add workspace_id (close latent cross-tenant collision)

The 0005 unique key ``(name_a, type_a, name_b, type_b)`` is enforced by an index that sees
ALL rows, *below* Row-Level Security. So the SAME conflict pair proposed in a second
workspace collided with the first tenant's row — a cross-tenant write coupling: workspace B
could be refused an insert because workspace A already holds that pair, even though neither
can see the other's rows. Latent today (detection runs default-workspace only) but a real
isolation defect once detection is multi-tenant.

Adding ``workspace_id`` to the key makes conflict identity per-workspace, matching every other
tenant-owned constraint. Detection already stamps ``workspace_id`` explicitly (F2 /
meridian-p1.0.1), so no code change is needed — this migration only widens the uniqueness scope.

The old constraint name below is Postgres's auto-generated name from 0005, verified against the
live schema before writing this migration. Revision id kept <= 32 chars (alembic_version column).

Revision ID: 0006_conflict_workspace_uq
Revises: 0005_entity_conflict
Create Date: 2026-07-20
"""
from alembic import op

revision = "0006_conflict_workspace_uq"
down_revision = "0005_entity_conflict"
branch_labels = None
depends_on = None

_OLD = "entity_conflict_name_a_type_a_name_b_type_b_key"  # auto-name from 0005 (verified)
_NEW = "uq_entity_conflict_workspace_names"               # explicit name for future reference


def upgrade() -> None:
    op.execute(f"ALTER TABLE entity_conflict DROP CONSTRAINT IF EXISTS {_OLD}")
    op.execute(
        f"ALTER TABLE entity_conflict ADD CONSTRAINT {_NEW} "
        "UNIQUE (workspace_id, name_a, type_a, name_b, type_b)"
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE entity_conflict DROP CONSTRAINT IF EXISTS {_NEW}")
    op.execute(
        f"ALTER TABLE entity_conflict ADD CONSTRAINT {_OLD} "
        "UNIQUE (name_a, type_a, name_b, type_b)"
    )
