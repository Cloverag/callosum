"""resolution, resolution_vote — the formal instrument (Meridian P2, checkpoint 6)

A Decision is what the board concluded. A Resolution is the formal instrument that
records it. FR-EXEC-02 requires three things stay separable — a draft action item,
a formally adopted resolution, and an external task — and CP6 delivers the middle
one. CP7's `commitment` is the third; the first is already `agenda_item`.

Adopted resolutions are frozen. Amendment creates a new version via
`supersede_resolution`, exactly as `board_pack` and `minutes` do.

DELIBERATELY OUT OF SCOPE: e-signature, legal validity, jurisdiction. `signing_state`
exists as a single-value enum so P8 has somewhere to land, and it is pinned to
`not_applicable` here precisely so nothing in this release can claim a resolution was
legally executed. Widening that enum is P8's work, not a migration detail.

Revision ID: 0014_resolution
Revises: 0013_principal_rls
Create Date: 2026-07-28
"""
from alembic import op

revision = "0014_resolution"
down_revision = "0013_principal_rls"
branch_labels = None
depends_on = None

DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
_PREDICATE = "workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid"

# `draft` -> `adopted` | `rejected`; `adopted` leaves only via supersession.
# No `archived`: CP5a's review flagged that a status nothing transitions out of is
# the `deferred` mistake repeating, and issue #23 left "does archived earn its
# place" open. It does not earn it here — a superseded resolution is already
# distinguishable by `superseded_by_id`, so `archived` would be a second way to
# say the same thing.
_STATUSES = "('draft', 'adopted', 'rejected', 'superseded')"

# Per-motion, unlike `board_member.voting`, which is a STANDING status. A director
# who is generally `voting` can be recused from one motion, and that fact belongs
# to the vote. CP5a explicitly deferred this here.
_VOTES = "('for', 'against', 'abstain', 'recused')"

# One value on purpose. See the module docstring.
_SIGNING_STATES = "('not_applicable')"


def upgrade() -> None:
    # `decision` predates the composite-FK house rule and has no (id, workspace_id)
    # unique constraint, so there is nothing for a composite FK to target. Adding
    # the target here rather than editing 0009, which is frozen.
    #
    # This is additive and cannot fail on existing rows: `id` is already the primary
    # key, so (id, workspace_id) is unique for free. It exists solely as an FK target.
    op.execute(
        """
        ALTER TABLE decision
            ADD CONSTRAINT decision_id_workspace_uq UNIQUE (id, workspace_id)
        """
    )

    op.execute(
        f"""
        CREATE TABLE resolution (
            id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            workspace_id      UUID NOT NULL DEFAULT '{DEFAULT_WORKSPACE_ID}' REFERENCES workspace(id),
            decision_id       UUID NOT NULL,
            title             TEXT NOT NULL,
            body              TEXT NOT NULL,
            status            TEXT NOT NULL DEFAULT 'draft' CHECK (status IN {_STATUSES}),
            signing_state     TEXT NOT NULL DEFAULT 'not_applicable'
                                  CHECK (signing_state IN {_SIGNING_STATES}),
            version_no        INT NOT NULL DEFAULT 1,
            superseded_by_id  UUID REFERENCES resolution(id) ON DELETE SET NULL,
            adopted_at        TIMESTAMPTZ,
            version           INT NOT NULL DEFAULT 1,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT resolution_title_not_empty CHECK (length(trim(title)) > 0),
            CONSTRAINT resolution_body_not_empty CHECK (length(trim(body)) > 0),

            -- The FK target for resolution_vote, same role as
            -- board_member_id_workspace_uq. Not a uniqueness rule in its own right.
            CONSTRAINT resolution_id_workspace_uq UNIQUE (id, workspace_id),

            -- Composite, per the CONTRIBUTING.md standing rule. A single-column
            -- REFERENCES decision(id) would be validated as the table owner, which
            -- bypasses RLS, and would let a resolution in one workspace attach
            -- itself to another workspace's decision.
            CONSTRAINT resolution_decision_fk
                FOREIGN KEY (decision_id, workspace_id)
                REFERENCES decision (id, workspace_id)
                ON DELETE RESTRICT
        )
        """
    )
    op.execute("CREATE INDEX ix_resolution_workspace ON resolution (workspace_id)")
    op.execute("CREATE INDEX ix_resolution_decision ON resolution (decision_id)")

    op.execute(
        f"""
        CREATE TABLE resolution_vote (
            id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            workspace_id     UUID NOT NULL DEFAULT '{DEFAULT_WORKSPACE_ID}' REFERENCES workspace(id),
            resolution_id    UUID NOT NULL,
            board_member_id  UUID NOT NULL,
            vote             TEXT NOT NULL CHECK (vote IN {_VOTES}),
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

            -- A director gets one vote per motion. Changing it updates this row;
            -- `created_at` records when they first voted and is never rewritten,
            -- which is the p1.0.5 review finding on decision_stance applied here
            -- from the start rather than fixed afterwards.
            CONSTRAINT resolution_vote_unique_member UNIQUE (resolution_id, board_member_id),

            CONSTRAINT resolution_vote_resolution_fk
                FOREIGN KEY (resolution_id, workspace_id)
                REFERENCES resolution (id, workspace_id)
                ON DELETE CASCADE,

            -- RESTRICT rather than CASCADE: the directory rule is
            -- deactivate-never-delete, so deleting a member who has voted should
            -- fail loudly rather than silently erase the voting record.
            CONSTRAINT resolution_vote_board_member_fk
                FOREIGN KEY (board_member_id, workspace_id)
                REFERENCES board_member (id, workspace_id)
                ON DELETE RESTRICT
        )
        """
    )
    op.execute("CREATE INDEX ix_resolution_vote_workspace ON resolution_vote (workspace_id)")
    op.execute("CREATE INDEX ix_resolution_vote_resolution ON resolution_vote (resolution_id)")
    op.execute("CREATE INDEX ix_resolution_vote_member ON resolution_vote (board_member_id)")

    for tbl in ("resolution", "resolution_vote"):
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {tbl}
                FOR ALL
                USING ({_PREDICATE})
                WITH CHECK ({_PREDICATE})
            """
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {tbl} TO callosum_app")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON resolution_vote")
    op.execute("DROP TABLE IF EXISTS resolution_vote")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON resolution")
    op.execute("DROP TABLE IF EXISTS resolution")
    op.execute("ALTER TABLE decision DROP CONSTRAINT IF EXISTS decision_id_workspace_uq")
