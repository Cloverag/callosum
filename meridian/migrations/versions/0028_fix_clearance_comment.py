"""correct 0013's principal.clearance comment — role, not membership.clearance, is authoritative

`0013_principal_rls` left a `COMMENT ON COLUMN principal.clearance` reading:

    Runtime authorization reads membership.clearance for the active workspace
    (see callosum.identity.resolve_principal). Do not read this column to make
    an access decision — clearance is per-workspace.

That was correct when written (checkpoint 5b moved authorization from
`principal.clearance` to `membership.clearance`), and is now itself wrong: #166 moved
authorization again, from `membership.clearance` to `membership.role`, mapped through
`callosum.identity.ROLE_TO_CLEARANCE`. `identity.py`'s `_PRINCIPAL_WITH_ACTIVE_MEMBERSHIP`
no longer selects `membership.clearance` at all as of the same commit that adds this
migration — so the comment is not "soon to be wrong", it is wrong the instant that code
merges, independent of what happens to the `membership.clearance` column itself.

WHY THIS MIGRATION, AND NOT THE FUTURE ONE THAT TOUCHES THE COLUMN
--------------------------------------------------------------------------------
The ruling (`docs/reviews/2026-09-03-p4-membership-decision-brief.md` §11 Q1, "make role
authoritative first, migrate consumers, and only then demote or remove the column in a
*separate* migration") is about `membership.clearance` — whether it keeps existing,
keeps being written, or is dropped. This migration does not touch that column: it
corrects a comment on a *different* column (`principal.clearance`) that makes a claim
about which table authorization reads. That claim is already false the moment
`identity.py` changes, so deferring the correction to the same later migration that
decides `membership.clearance`'s fate would leave a comment lying about the current
state of the database for however long that later work takes — the opposite of what
`0013` gave the reason for writing this comment at all ("the difference between
'documented' and 'discoverable'").

CHAINED AFTER `0027` — AFTER TWO REVERSALS, AND WHY EACH ONE HAPPENED
--------------------------------------------------------------------------------
First written with `down_revision = "0027_membership_role_and_audit"`, on the reasoning
that `0027` (PR #180) will exist in any real database this applies to before this
migration does. That is true of a *deployed* database, but alembic resolves its whole
revision graph from the files physically present in `versions/` before running anything
— not only the file being applied — and at that point `0027`'s file lived on a separate,
unmerged branch. With that `down_revision`, this branch could not run `alembic upgrade`,
`alembic current`, or anything else that touches the graph AT ALL, migration content
aside: `KeyError: '0027_membership_role_and_audit'` on load, before any SQL ran. Found
by trying it, not by reasoning about it — the same way the naming length limit below was
found. So it was reverted to `0026`, which kept this branch independently runnable.

That reversion was correct for an unmerged `0027` and created a known cost, recorded at
the time: two migrations both revising `0026`, an actual multi-head the moment both
existed in one tree. #180 merged first (master `388de8f`), so `0027`'s file is now
physically present in `versions/` and the reason for parenting to `0026` is gone. Chained
to `0027` here, which resolves the multi-head by ordering rather than by a merge
migration — the two are content-independent (different tables, different columns: this
one comments `principal.clearance`, `0027` constrains `membership.role` and widens
`audit_event.aggregate_type`), so either order was correct and this is simply the order
they merged in.

Nothing about the SQL changed across either reversal. The only order dependency this
migration has ever had is on *code*, not schema: the comment's new text is true because
this branch's `identity.py` reads `membership.role` through
`callosum.identity.ROLE_TO_CLEARANCE`, and that lands in the same commit as this file.

NAMED SHORTER THAN THE OBVIOUS CHOICE, AND WHY
--------------------------------------------------------------------------------
Same `varchar(32)` limit on `alembic_version.version_num` that renamed `0027` in this
same session. `0028_correct_principal_clearance_comment` (40 chars) hit the identical
`StringDataRightTruncation`, caught the same way — by running it, transaction rolled
back cleanly, comment still read the pre-migration text afterward. Shortened to
`0028_fix_clearance_comment` (26 chars).

Revision ID: 0028_fix_clearance_comment
Revises: 0027_membership_role_and_audit
Create Date: 2026-09-03
"""
from alembic import op

revision = "0028_fix_clearance_comment"
down_revision = "0027_membership_role_and_audit"
branch_labels = None
depends_on = None

_OLD_COMMENT = (
    "LEGACY / bootstrap seed only. Runtime authorization reads membership.clearance "
    "for the active workspace (see callosum.identity.resolve_principal). Do not read "
    "this column to make an access decision — clearance is per-workspace."
)

_NEW_COMMENT = (
    "LEGACY / bootstrap seed only. Runtime authorization reads membership.role, mapped "
    "to a clearance via callosum.identity.ROLE_TO_CLEARANCE (see "
    "callosum.identity.resolve_principal) — not membership.clearance, which is stored "
    "but no longer read for authorization (#166). Do not read this column to make an "
    "access decision — clearance is derived from role, and is per-workspace."
)


def upgrade() -> None:
    op.execute(f"COMMENT ON COLUMN principal.clearance IS '{_NEW_COMMENT}'")


def downgrade() -> None:
    op.execute(f"COMMENT ON COLUMN principal.clearance IS '{_OLD_COMMENT}'")
