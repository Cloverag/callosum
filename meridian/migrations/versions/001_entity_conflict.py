"""entity_conflict

Revision ID: 001_entity_conflict
Revises: 
Create Date: 2026-07-18 19:50:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001_entity_conflict'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS entity_conflict (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        name_a          TEXT NOT NULL,
        type_a          TEXT NOT NULL,
        name_b          TEXT NOT NULL,
        type_b          TEXT NOT NULL,
        similarity      REAL NOT NULL,
        chunk_id_a      UUID REFERENCES chunk(id) ON DELETE SET NULL,
        chunk_id_b      UUID REFERENCES chunk(id) ON DELETE SET NULL,
        quote_a         TEXT,
        quote_b         TEXT,
        sensitivity     INT NOT NULL DEFAULT 1 REFERENCES sensitivity(level),
        status          TEXT NOT NULL DEFAULT 'pending',
        reviewed_by     UUID REFERENCES principal(id),
        reviewed_at     TIMESTAMPTZ,
        change_id       UUID REFERENCES proposed_change(id),
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (name_a, type_a, name_b, type_b)
    );

    CREATE INDEX IF NOT EXISTS entity_conflict_status_idx ON entity_conflict (status);
    CREATE INDEX IF NOT EXISTS entity_conflict_sensitivity_idx ON entity_conflict (sensitivity);
    """)


def downgrade() -> None:
    op.execute("""
    DROP INDEX IF EXISTS entity_conflict_sensitivity_idx;
    DROP INDEX IF EXISTS entity_conflict_status_idx;
    DROP TABLE IF EXISTS entity_conflict;
    """)
