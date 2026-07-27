"""board_member — governance directory (Meridian P2, checkpoint 5a)

The people who participate in a board, per PRD FR-WS-03: name, organization,
role, contact method, voting status, active/inactive.

This is NOT `membership`. `membership` is the auth fact — principal x workspace
-> role, clearance — and requires a login. `board_member` is the governance
directory, and a non-executive director who never signs in must still be
recordable, votable, and assignable. Hence the nullable `principal_id`.

Deliberately carries NO clearance column. Clearance belongs to `membership` by
the P1 design; two sources of truth for clearance is how RBAC gets bypassed.
(That `membership` is currently unpopulated is CP5b's problem — see issue #40 —
and is not a reason to duplicate the column here.)

Revision ID: 0012_board_member
Revises: 0011_control_plane_rls
Create Date: 2026-07-28
"""
from alembic import op

revision = "0012_board_member"
down_revision = "0011_control_plane_rls"
branch_labels = None
depends_on = None

DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
_PREDICATE = "workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid"

# FR-WS-02.
_ROLES = "('director', 'observer', 'executive', 'administrator', 'adviser')"

# FR-WS-03 calls this "voting status", and an enum rather than a boolean because
# `recused` is a real third state, not an absence of voting rights. This is the
# member's STANDING status; per-motion recusal is a property of the vote and
# belongs on `resolution_vote` in CP6.
_VOTING = "('voting', 'non_voting', 'recused')"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE board_member (
            id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            workspace_id   UUID NOT NULL DEFAULT '{DEFAULT_WORKSPACE_ID}' REFERENCES workspace(id),
            principal_id   UUID REFERENCES principal(id) ON DELETE SET NULL,
            full_name      TEXT NOT NULL,
            organization   TEXT,
            role           TEXT NOT NULL CHECK (role IN {_ROLES}),
            contact_email  TEXT,
            voting         TEXT NOT NULL DEFAULT 'voting' CHECK (voting IN {_VOTING}),
            active         BOOLEAN NOT NULL DEFAULT true,
            version        INT NOT NULL DEFAULT 1,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT board_member_name_not_empty CHECK (length(trim(full_name)) > 0)
        )
        """
    )
    # No UNIQUE on (workspace_id, full_name), deliberately. Two real people can
    # share a name, and this system's alias/ALIAS_OF machinery exists precisely
    # because names collide. A unique key would make the tidy case tidier and the
    # correct case impossible.
    op.execute("CREATE INDEX ix_board_member_workspace ON board_member (workspace_id)")
    op.execute("CREATE INDEX ix_board_member_active ON board_member (workspace_id, active)")

    op.execute("ALTER TABLE board_member ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE board_member FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON board_member
            FOR ALL
            USING ({_PREDICATE})
            WITH CHECK ({_PREDICATE})
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON board_member TO callosum_app")

    # --- resolve stances to the directory, optionally and forever -----------
    #
    # `decision_stance.person_name` STAYS, and this column is NEVER made NOT NULL.
    # They answer different questions: `person_name` is the name as recorded when
    # the stance was taken, which is audit data the immutability contract keeps;
    # `board_member_id` is an optional resolution of that string to a directory
    # entry. Collapsing them would lose the record of what was actually minuted.
    op.execute(
        "ALTER TABLE decision_stance "
        "ADD COLUMN board_member_id UUID REFERENCES board_member(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX ix_decision_stance_board_member ON decision_stance (board_member_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_decision_stance_board_member")
    op.execute("ALTER TABLE decision_stance DROP COLUMN IF EXISTS board_member_id")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON board_member")
    op.execute("DROP TABLE IF EXISTS board_member")
