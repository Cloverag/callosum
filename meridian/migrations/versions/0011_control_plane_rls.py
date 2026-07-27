"""control-plane RLS — workspace, membership, sensitivity (issue #32)

Closes an unmet P1 exit criterion, not new P2 scope. P1 requires unauthorized
content be blocked "in SQL", and these four control-plane tables shipped with no
row-level security while `callosum_app` held SELECT/INSERT/UPDATE/DELETE on all
of them. A connection scoped to one workspace could enumerate every other
tenant's name, members, roles and clearance levels.

Content tables were never affected — all thirteen carry ENABLE + FORCE + a
tenant policy, and the isolation tests prove it. This is the control plane only.

WHAT THIS DOES NOT FIX: `principal` is deliberately left alone. See the note
below; it needs work this migration cannot safely do.

Revision ID: 0011_control_plane_rls
Revises: 0010_board_pack
Create Date: 2026-07-28
"""
from alembic import op

revision = "0011_control_plane_rls"
down_revision = "0010_board_pack"
branch_labels = None
depends_on = None

_PREDICATE = "workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid"
# `workspace` is keyed on its own id rather than a workspace_id column: a scoped
# connection may see exactly the workspace row it is scoped to.
_WORKSPACE_PREDICATE = "id = NULLIF(current_setting('app.workspace_id', true), '')::uuid"


def upgrade() -> None:
    # --- membership + workspace: full tenant isolation ----------------------
    #
    # Neither table has a runtime reader — `grep` finds no SELECT of either in
    # `src/callosum/` or `meridian/`. They are written by migrations and by tests
    # through the `_admin` superuser control plane, both of which bypass RLS by
    # design. So enabling FORCE here costs nothing and closes the enumeration path.
    for tbl, predicate in (("membership", _PREDICATE), ("workspace", _WORKSPACE_PREDICATE)):
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {tbl}
                FOR ALL
                USING ({predicate})
                WITH CHECK ({predicate})
            """
        )
        # Least privilege: the runtime role reads the control plane, it does not
        # edit it. Membership and workspace changes are administrative operations
        # and belong on the superuser path with the migrations.
        op.execute(f"REVOKE INSERT, UPDATE, DELETE ON {tbl} FROM callosum_app")

    # --- sensitivity: read-only, no RLS -------------------------------------
    #
    # A static lookup of the five clearance levels. It has no tenant dimension, so
    # a tenant predicate would be meaningless — but nothing at runtime should be
    # editing the clearance ladder, and `callosum_app` could.
    op.execute("REVOKE INSERT, UPDATE, DELETE ON sensitivity FROM callosum_app")

    # --- principal: DELIBERATELY UNTOUCHED ----------------------------------
    #
    # `principal` is the remaining gap and it is recorded rather than papered over.
    #
    # The correct policy is membership-derived — a principal is visible in a
    # workspace iff they hold a membership there — because `membership`'s primary
    # key is (principal_id, workspace_id), so one person legitimately belongs to
    # several workspaces and a `workspace_id` column on `principal` would be wrong.
    #
    # That policy cannot be applied yet, because NOTHING EVER CREATES A MEMBERSHIP
    # ROW. `callosum init` seeds principals and no memberships; no migration
    # backfills them; runtime clearance is read straight off `principal.clearance`
    # in `cli.py`. A membership-derived policy today would therefore hide every
    # principal from every caller and break the CLI outright.
    #
    # So scoping `principal` requires first wiring membership for real: seeding it
    # at bootstrap, moving `callosum init` to the admin connection (it is a
    # bootstrap command using the runtime role), and resolving clearance through
    # membership rather than `principal`. That is a reviewed change of its own, and
    # it belongs with CP5 (issue #36), which is precisely about the people model.
    #
    # Residual exposure until then: a runtime caller can enumerate the global
    # person directory — names, emails, roles, clearance values. It can no longer
    # learn WHICH WORKSPACE any of them belong to, which was the demonstrated leak.


def downgrade() -> None:
    op.execute("GRANT INSERT, UPDATE, DELETE ON sensitivity TO callosum_app")
    for tbl in ("workspace", "membership"):
        op.execute(f"GRANT INSERT, UPDATE, DELETE ON {tbl} TO callosum_app")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {tbl}")
        op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY")
