"""dedupe_contradictory_fks — one delete rule per relationship, and it is refuse (Issue #165)

Revision ID: 0026_dedupe_contradictory_fks
Revises: 0025_meeting_document
Create Date: 2026-08-25 07:40:00.000000

Five relationships carry **two** composite foreign keys over the same columns, against
the same target, with **contradictory `ON DELETE`**. Postgres fires every matching
constraint, so the strictest wins: `RESTRICT` has been governing all five, and
`0021_fix_composite_fk_cascades` has been silently defeated since it was written.

HOW THE DUPLICATES AROSE
------------------------
`0014`/`0015` created composite FKs named `commitment_decision_fk`,
`resolution_decision_fk`, and so on. `0019` then added its own composite FKs under
`*_workspace_fk` names, dropping only the *single-column* `*_id_fkey` constraints it
knew about — the `0014`/`0015` composites had different names and survived. `0021`
later gave the `*_workspace_fk` half its cascade semantics, against a duplicate nobody
had noticed.

Nothing was wrong in any one migration. The defect is only visible in the catalog,
which is why reading migrations found three of these and `pg_constraint` found five.

WHAT THIS CHANGES AT RUNTIME: NOTHING
-------------------------------------
`RESTRICT` already governs. Verified on a live database before this was written —
deleting a decision with a dependent resolution was refused, by the RESTRICT side.
This migration removes the contradiction and makes the surviving rule the stated one.
It does not change what the database does.

WHY REFUSE AND NOT CASCADE
--------------------------
The maintainer's call, per pair rather than as one policy. The common thread:
cascading here destroys the record of how the board reached a position. A resolution
vote **is** the evidence that a resolution passed; a commitment is the obligation a
decision created. Removing the parent should not quietly remove the proof.

`RESTRICT` makes the refusal explicit and forces a caller who really means it to
unpick the dependants first — deliberately, and in the audit trail.

WHAT IS KNOWINGLY LEFT
----------------------
Two relationships still carry two constraints each after this migration:

    commitment_update -> commitment      CASCADE on both sides
    resolution_vote   -> resolution      CASCADE on both sides

They are **redundant, not contradictory** — both sides agree, so behaviour is
unambiguous and there is nothing to resolve today. They are left because removing a
constraint that changes nothing is a schema change with no benefit, and because the
one that would survive is not obviously either of them.

But the *condition* that produced the five is still standing on these two: two
constraints on one relationship, with nothing forcing them to agree. **If a later
migration alters one side of either, it becomes a sixth contradiction silently** — the
same way `0021` created five without anyone noticing. Recorded here so that a reader
running the duplicate sweep afterwards can tell a decision from an oversight.

The sweep, for whoever runs it next:

    SELECT c.conrelid::regclass AS tbl, c.conname, c.confdeltype
      FROM pg_constraint c
     WHERE c.contype = 'f' AND connamespace = 'public'::regnamespace
     ORDER BY tbl, c.conname;

TENANT ISOLATION IS UNAFFECTED
------------------------------
Both members of every pair are composite `(x_id, workspace_id) REFERENCES t(id,
workspace_id)`. The survivor is as composite as the constraint dropped, so the
protection CONTRIBUTING.md describes — a single-column FK is validated as the table
owner and bypasses RLS — is untouched. Checked with `pg_get_constraintdef` on all ten
before writing this, not inferred from the names.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0026_dedupe_contradictory_fks"
down_revision = "0025_meeting_document"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        -- 1. commitment -> decision.  RESTRICT (0014) vs CASCADE (0021).
        --    A commitment is what a decision obliged someone to do. Deleting the
        --    decision must not silently delete the obligations it created.
        ALTER TABLE commitment DROP CONSTRAINT IF EXISTS commitment_decision_workspace_fk;

        -- 2. commitment -> resolution.  RESTRICT (0015) vs SET NULL (0021).
        --    SET NULL is the worst of the three here: it would leave the commitment
        --    standing while erasing which resolution authorised it, turning a
        --    traceable obligation into an unattributed one.
        ALTER TABLE commitment DROP CONSTRAINT IF EXISTS commitment_resolution_workspace_fk;

        -- 3. commitment -> board_member (owner).  RESTRICT (0015) vs CASCADE (0021).
        --    Inert today — board members are never hard-deleted, `deactivate_member`
        --    exists precisely so they are not. Kept consistent rather than left as the
        --    one pair whose rule differs for no reason a reader could reconstruct.
        ALTER TABLE commitment DROP CONSTRAINT IF EXISTS commitment_owner_workspace_fk;

        -- 4. resolution -> decision.  RESTRICT (0014) vs CASCADE (0021).
        --    The resolution is the formal act; the decision is its subject. Deleting
        --    the subject should not erase the act.
        ALTER TABLE resolution DROP CONSTRAINT IF EXISTS resolution_decision_workspace_fk;

        -- 5. resolution_vote -> board_member.  RESTRICT (0014) vs CASCADE (0021).
        --    The sharpest of the five. Cascading a board-member deletion would destroy
        --    the votes recording how a resolution passed — the quorum evidence — and
        --    a board record must not do that quietly. Also inert today, for the same
        --    reason as 3.
        ALTER TABLE resolution_vote DROP CONSTRAINT IF EXISTS resolution_vote_member_workspace_fk;
        """
    )


def downgrade() -> None:
    """Restore exactly the five constraints dropped above, with their original semantics.

    Only these five, and only as they were. `0019` created them without an `ON DELETE`
    clause and `0021` gave them the cascade semantics reproduced here, so this restores
    the post-`0021` state — which is what `upgrade()` removed, and the only state a
    reverse leg through this revision can correctly return to.

    Recreating them re-introduces the contradiction on purpose: a downgrade returns the
    schema to what it was, including its defects. Fixing on the way down would leave a
    database that had gone down and back up differing from one that never moved, which
    is the failure `scripts/schema_fingerprint.py` exists to catch.
    """
    op.execute(
        """
        ALTER TABLE commitment
            ADD CONSTRAINT commitment_decision_workspace_fk
                FOREIGN KEY (decision_id, workspace_id)
                REFERENCES decision(id, workspace_id) ON DELETE CASCADE,
            ADD CONSTRAINT commitment_resolution_workspace_fk
                FOREIGN KEY (resolution_id, workspace_id)
                REFERENCES resolution(id, workspace_id) ON DELETE SET NULL,
            ADD CONSTRAINT commitment_owner_workspace_fk
                FOREIGN KEY (owner_board_member_id, workspace_id)
                REFERENCES board_member(id, workspace_id) ON DELETE CASCADE;

        ALTER TABLE resolution
            ADD CONSTRAINT resolution_decision_workspace_fk
                FOREIGN KEY (decision_id, workspace_id)
                REFERENCES decision(id, workspace_id) ON DELETE CASCADE;

        ALTER TABLE resolution_vote
            ADD CONSTRAINT resolution_vote_member_workspace_fk
                FOREIGN KEY (board_member_id, workspace_id)
                REFERENCES board_member(id, workspace_id) ON DELETE CASCADE;
        """
    )
