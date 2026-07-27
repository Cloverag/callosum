"""enable Row-Level Security and revoke write grants on control-plane tables (Issue #32)

Hardens the 4 control-plane tables:
  * membership — ENABLE + FORCE RLS, tenant policy workspace_id = session app.workspace_id, REVOKE write grants
  * workspace  — ENABLE + FORCE RLS, tenant policy id = session app.workspace_id, REVOKE write grants
  * principal  — ENABLE + FORCE RLS, subquery policy joining membership for tenant principal visibility, REVOKE write grants
  * sensitivity — static lookup table, REVOKE write grants from callosum_app

Revision ID: 0011_control_plane_rls
Revises: 0010_board_pack
Create Date: 2026-07-27
"""

from alembic import op

revision = "0011_control_plane_rls"
down_revision = "0010_board_pack"
branch_labels = None
depends_on = None

_MEMBERSHIP_PREDICATE = "workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid"
_WORKSPACE_PREDICATE = "id = NULLIF(current_setting('app.workspace_id', true), '')::uuid"
_PRINCIPAL_PREDICATE = (
    "EXISTS (SELECT 1 FROM membership m WHERE m.principal_id = id AND m.workspace_id = "
    "NULLIF(current_setting('app.workspace_id', true), '')::uuid)"
)


def upgrade() -> None:
    # 1. membership table RLS + revoke write grants
    op.execute("ALTER TABLE membership ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE membership FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON membership
            FOR ALL
            USING ({_MEMBERSHIP_PREDICATE})
            WITH CHECK ({_MEMBERSHIP_PREDICATE})
        """
    )
    op.execute("REVOKE INSERT, UPDATE, DELETE ON membership FROM callosum_app")

    # 2. workspace table RLS + revoke write grants
    op.execute("ALTER TABLE workspace ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workspace FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON workspace
            FOR ALL
            USING ({_WORKSPACE_PREDICATE})
            WITH CHECK ({_WORKSPACE_PREDICATE})
        """
    )
    op.execute("REVOKE INSERT, UPDATE, DELETE ON workspace FROM callosum_app")

    # 3. principal table RLS + revoke write grants
    op.execute("ALTER TABLE principal ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE principal FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON principal
            FOR ALL
            USING ({_PRINCIPAL_PREDICATE})
            WITH CHECK ({_PRINCIPAL_PREDICATE})
        """
    )
    op.execute("REVOKE INSERT, UPDATE, DELETE ON principal FROM callosum_app")

    # 4. sensitivity lookup table revoke write grants
    op.execute("REVOKE INSERT, UPDATE, DELETE ON sensitivity FROM callosum_app")


def downgrade() -> None:
    # 1. Re-grant write privileges to callosum_app
    op.execute("GRANT INSERT, UPDATE, DELETE ON sensitivity TO callosum_app")
    op.execute("GRANT INSERT, UPDATE, DELETE ON principal TO callosum_app")
    op.execute("GRANT INSERT, UPDATE, DELETE ON workspace TO callosum_app")
    op.execute("GRANT INSERT, UPDATE, DELETE ON membership TO callosum_app")

    # 2. Drop policies and disable RLS
    for table in ("principal", "workspace", "membership"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
