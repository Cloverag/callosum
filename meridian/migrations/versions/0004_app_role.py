"""create the non-superuser runtime role so RLS actually enforces (Meridian P1, brick 2b.2)

Enabling RLS in 0003 was necessary but not sufficient: the app was connecting as the
`callosum` role, which POSTGRES_USER makes a SUPERUSER, and superusers bypass RLS
unconditionally — FORCE has no power over them. So every policy was silently skipped.

The fix is a two-role split:

  * callosum       (superuser)      — migrations, init, admin. Bypasses RLS (that's fine;
                                       it is the trusted control plane).
  * callosum_app   (NOSUPERUSER,    — the RUNNING application (store.pg). Subject to RLS,
                    NOBYPASSRLS)       so tenant isolation is actually enforced.

This migration only creates the role and grants it DML on the current + future tables.
The application is pointed at it in a companion code change (config.postgres_app_dsn +
store.pg). The frozen eval then runs as callosum_app too, which is what makes the
"identical metrics" check in brick 2b.5 a REAL proof that RLS is a single-tenant no-op.

Revision ID: 0004_app_role
Revises: 0003_enable_rls
Create Date: 2026-07-19
"""
from alembic import op

revision = "0004_app_role"
down_revision = "0003_enable_rls"
branch_labels = None
depends_on = None

# Local-dev credentials. In a real deployment these come from the environment /
# secrets manager, never a literal — see config.postgres_app_dsn.
APP_ROLE = "callosum_app"
APP_PASSWORD = "callosum_app"


def upgrade() -> None:
    # CREATE ROLE is not idempotent, so guard it (fresh volumes re-run every migration).
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{APP_PASSWORD}'
                    NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
            END IF;
        END
        $$
        """
    )

    # Runtime privileges: read/write data, but no DDL and no role management.
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")

    # Future tables/sequences created by the admin role (e.g. the entity_conflict
    # migration) auto-grant to the app role, so we never have to remember to re-grant.
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}"
    )


def downgrade() -> None:
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {APP_ROLE}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE USAGE, SELECT ON SEQUENCES FROM {APP_ROLE}"
    )
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}")
    op.execute(f"DROP ROLE IF EXISTS {APP_ROLE}")
