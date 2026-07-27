"""principal RLS via membership — closes the p1.0.5 gap (Meridian P2, checkpoint 5b)

`p1.0.5` (#38) put row-level security on `membership`, `workspace` and
`sensitivity` but deliberately left `principal` alone, because the correct policy
is membership-derived and **nothing ever created a membership row**. A policy
keyed on an empty table hides every principal from every caller and breaks the
CLI outright.

CP5b wires membership for real — `callosum init` seeds it on the admin connection
and `callosum.identity` resolves clearance through it — so the policy can now be
applied.

Revision ID: 0013_principal_rls
Revises: 0012_board_member
Create Date: 2026-07-28
"""
from alembic import op

revision = "0013_principal_rls"
down_revision = "0012_board_member"
branch_labels = None
depends_on = None

# A person is visible in a workspace iff they hold a membership there.
#
# It cannot be a `workspace_id` column on `principal`: membership's primary key is
# (principal_id, workspace_id), so one individual legitimately belongs to several
# workspaces and a single column would force a choice that does not exist.
#
# Note this composes with membership's own RLS from 0011 — the subquery is already
# workspace-scoped, so the explicit predicate is belt-and-braces. It is kept
# because it is self-documenting and does not silently depend on another table's
# policy remaining as it is.
_PREDICATE = """
    EXISTS (
        SELECT 1 FROM membership m
         WHERE m.principal_id = principal.id
           AND m.workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid
    )
"""


def upgrade() -> None:
    op.execute("ALTER TABLE principal ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE principal FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON principal
            FOR ALL
            USING ({_PREDICATE})
            WITH CHECK ({_PREDICATE})
        """
    )
    # The only writer was `callosum init`, which CP5b moved onto the admin
    # connection where bootstrap belongs. Nothing at runtime creates people.
    op.execute("REVOKE INSERT, UPDATE, DELETE ON principal FROM callosum_app")

    # `principal.clearance` is now a bootstrap seed value, not an authorization
    # input. `callosum.identity.resolve_principal` reads clearance from the
    # membership and never from here.
    #
    # The column is kept rather than dropped for two reasons: it is declared in
    # the frozen `schema/postgres.sql`, and `callosum init` still uses it as the
    # source value when seeding memberships. Recording the demotion in the
    # database itself — rather than only in a doc — means `\d+ principal` tells
    # the next reader, which is the difference between "documented" and
    # "discoverable".
    op.execute(
        """
        COMMENT ON COLUMN principal.clearance IS
          'LEGACY / bootstrap seed only. Runtime authorization reads membership.clearance '
          'for the active workspace (see callosum.identity.resolve_principal). Do not read '
          'this column to make an access decision — clearance is per-workspace.'
        """
    )


def downgrade() -> None:
    op.execute("COMMENT ON COLUMN principal.clearance IS NULL")
    op.execute("GRANT INSERT, UPDATE, DELETE ON principal TO callosum_app")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON principal")
    op.execute("ALTER TABLE principal NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE principal DISABLE ROW LEVEL SECURITY")
