"""commitment, commitment_update — decision-to-execution (Meridian P2, checkpoint 7)

FR-EXEC-01: owner, accountable team, due date, status, source decision, and a
pointer back to the evidence. A commitment is the accountable work a decision
produced — the third of the three things FR-EXEC-02 requires stay separable
(draft action item = `agenda_item`, formal instrument = `resolution`, external
task = the delivery columns here).

FR-EXEC-03 — FAILED DELIVERY MUST NEVER FALSELY MARK AN ACTION DELIVERED — is
enforced by a CHECK constraint rather than by application code, so it holds even
against a direct SQL write. See `commitment_delivered_needs_external_ref` below.

Retry STATE is modelled here; retry EXECUTION is P8. `external_system`,
`external_task_id`, `delivery_status` and `delivery_attempts` are inert in this
release — nothing writes them except tests, and no adapter exists to dispatch.

Revision ID: 0015_commitment
Revises: 0014_resolution
Create Date: 2026-07-28
"""
from alembic import op

revision = "0015_commitment"
down_revision = "0014_resolution"
branch_labels = None
depends_on = None

DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
_PREDICATE = "workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid"

# The proposal specified `open -> in_progress -> {completed, blocked, cancelled}`.
# `blocked` is reachable from `open` too — work can be blocked before it starts —
# and, more importantly, `blocked` is NOT terminal here. A blocked task is
# expected to unblock; making it an exit would repeat the `deferred` (CP4) and
# `archived` (CP6) mistake of minting a status nothing can leave. Only `completed`
# and `cancelled` are terminal, and the module's transition table is the authority.
_STATUSES = "('open', 'in_progress', 'blocked', 'completed', 'cancelled')"

# `not_dispatched` is the default and the honest starting point: no adapter exists
# in P2, so every commitment is undispatched until P8 builds one.
_DELIVERY_STATUSES = "('not_dispatched', 'pending', 'delivered', 'failed')"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE commitment (
            id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            workspace_id            UUID NOT NULL DEFAULT '{DEFAULT_WORKSPACE_ID}'
                                        REFERENCES workspace(id),

            -- NOT NULL by design. The proposal's hard rule is that a commitment
            -- cannot exist without a source decision: untraceable work is exactly
            -- what this product exists to prevent.
            decision_id             UUID NOT NULL,

            -- The formal instrument, when the decision produced one. Nullable
            -- because not every decision is formalised as a resolution, and CP6
            -- resolutions are drafted independently of commitments.
            resolution_id           UUID,

            owner_board_member_id   UUID NOT NULL,
            accountable_team        TEXT,

            title                   TEXT NOT NULL,
            detail                  TEXT,

            -- DATE, not TIMESTAMPTZ: a deadline is a calendar day, and storing an
            -- instant would make "due Friday" mean different days for a board that
            -- spans timezones.
            due_date                DATE,

            status                  TEXT NOT NULL DEFAULT 'open' CHECK (status IN {_STATUSES}),
            completed_at            TIMESTAMPTZ,

            -- --- external linkage: inert in P2, P8 lands here -----------------
            external_system         TEXT,
            external_task_id        TEXT,
            delivery_status         TEXT NOT NULL DEFAULT 'not_dispatched'
                                        CHECK (delivery_status IN {_DELIVERY_STATUSES}),
            delivery_attempts       INT NOT NULL DEFAULT 0,

            version                 INT NOT NULL DEFAULT 1,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT commitment_title_not_empty CHECK (length(trim(title)) > 0),
            CONSTRAINT commitment_attempts_non_negative CHECK (delivery_attempts >= 0),

            -- FR-EXEC-03, AS A CONSTRAINT.
            --
            -- A commitment cannot be marked `delivered` without an external
            -- reference to point at. Enforcing this in Python would leave it true
            -- only for callers who went through the module; as a CHECK it holds
            -- against a direct SQL write, a bad migration, or a future adapter
            -- that forgets. `external_system` is required alongside the id because
            -- a task id with no system is unresolvable — it cannot be reconciled,
            -- which is the whole point of recording delivery.
            CONSTRAINT commitment_delivered_needs_external_ref CHECK (
                delivery_status <> 'delivered'
                OR (external_task_id IS NOT NULL AND external_system IS NOT NULL)
            ),

            CONSTRAINT commitment_id_workspace_uq UNIQUE (id, workspace_id),

            -- Composite, per the CONTRIBUTING.md standing rule: a single-column
            -- REFERENCES is validated as the table owner and bypasses RLS.
            CONSTRAINT commitment_decision_fk
                FOREIGN KEY (decision_id, workspace_id)
                REFERENCES decision (id, workspace_id)
                ON DELETE RESTRICT,

            CONSTRAINT commitment_resolution_fk
                FOREIGN KEY (resolution_id, workspace_id)
                REFERENCES resolution (id, workspace_id)
                ON DELETE RESTRICT,

            -- RESTRICT: the directory rule is deactivate-never-delete, so deleting
            -- a member who owns work should fail loudly rather than orphan it.
            CONSTRAINT commitment_owner_fk
                FOREIGN KEY (owner_board_member_id, workspace_id)
                REFERENCES board_member (id, workspace_id)
                ON DELETE RESTRICT
        )
        """
    )
    op.execute("CREATE INDEX ix_commitment_workspace ON commitment (workspace_id)")
    op.execute("CREATE INDEX ix_commitment_decision ON commitment (decision_id)")
    op.execute("CREATE INDEX ix_commitment_owner ON commitment (owner_board_member_id)")
    op.execute("CREATE INDEX ix_commitment_due ON commitment (workspace_id, due_date)")

    # Append-only. There is no update or delete path in the domain module: the
    # trail is the evidence that a commitment was worked, and an editable trail is
    # not evidence.
    op.execute(
        """
        CREATE TABLE commitment_update (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            workspace_id    UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001'
                                REFERENCES workspace(id),
            commitment_id   UUID NOT NULL,
            note            TEXT NOT NULL,

            -- The status the commitment moved to with this update, when it moved.
            -- NULL means the update recorded progress without changing state.
            new_status      TEXT,

            author_board_member_id UUID,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT commitment_update_note_not_empty CHECK (length(trim(note)) > 0),

            CONSTRAINT commitment_update_commitment_fk
                FOREIGN KEY (commitment_id, workspace_id)
                REFERENCES commitment (id, workspace_id)
                ON DELETE CASCADE,

            CONSTRAINT commitment_update_author_fk
                FOREIGN KEY (author_board_member_id, workspace_id)
                REFERENCES board_member (id, workspace_id)
                ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_commitment_update_commitment "
        "ON commitment_update (commitment_id, created_at)"
    )
    op.execute("CREATE INDEX ix_commitment_update_workspace ON commitment_update (workspace_id)")

    for tbl in ("commitment", "commitment_update"):
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
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON commitment_update")
    op.execute("DROP TABLE IF EXISTS commitment_update")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON commitment")
    op.execute("DROP TABLE IF EXISTS commitment")
