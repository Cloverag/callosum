"""document principal.role's demoted purpose — and name the caller that still reads it

#166 step 4. The one step of #166 that changes no behaviour: it writes down a demotion
that already happened, in the place a reader will find it.

--------------------------------------------------------------------------------
THE GAP
--------------------------------------------------------------------------------
#166 Q1 made `membership.role` authoritative and workspace-scoped, demoting
`principal.role` to legacy/global metadata. `0028_fix_clearance_comment` recorded the
matching demotion for `principal.clearance`. Nothing recorded this one:

    SELECT c.column_name,
           coalesce(col_description('principal'::regclass, c.ordinal_position),
                    '<<NO COMMENT>>')
      FROM information_schema.columns c
     WHERE c.table_name = 'principal';

    id         | <<NO COMMENT>>
    name       | <<NO COMMENT>>
    email      | <<NO COMMENT>>
    role       | <<NO COMMENT>>          <-- the column #166 Q1 demoted
    clearance  | LEGACY / bootstrap seed only. Runtime authorization reads ...
    org        | <<NO COMMENT>>
    created_at | <<NO COMMENT>>

Measured on merged master `e9dce16`. So of the pair `0028` describes as one decision,
the documented half is the one nobody asked about and the undocumented half is the one
the ruling was actually about.

`0013_principal_rls` gave the reason for writing these comments at all — "the
difference between 'documented' and 'discoverable'". A demotion recorded only in a
GitHub issue and a Python docstring is documented. A `COMMENT ON COLUMN` is
discoverable by someone reading the schema who has never seen either.

--------------------------------------------------------------------------------
WHAT THIS COMMENT DELIBERATELY DOES *NOT* SAY
--------------------------------------------------------------------------------
It does not say the column is unused, because it is not, and a comment that overstates
a demotion is worse than none — the next person to find a live reader concludes the
comment is stale and stops trusting the others beside it.

Two production readers survive on `e9dce16`, both named in the comment text:

  1. `src/callosum/cli.py:126` — `INSERT INTO membership (…) SELECT p.id, %s, p.role,
     p.clearance FROM principal p`. Bootstrap *propagation*: it seeds
     `membership.role` from this column. Not an access decision, and legitimate —
     `cli.py` is how the first memberships come to exist at all.

  2. `src/callosum/evaluate.py:408` — `SELECT id, name, role, clearance FROM principal
     WHERE name ILIKE %s`, feeding `Principal(role=row["role"],
     clearance=row["clearance"])` at `:413`. This one **is** an access decision: the
     object it builds is what `retrieve.py`'s frozen clearance gate receives.

The second is the one that matters, and it is the reason this comment is worded as
"do not read this column for an access decision" plus an explicit exception, rather
than as a flat prohibition the codebase does not honour.

--------------------------------------------------------------------------------
WHY `evaluate.py` IS NOT CHANGED HERE
--------------------------------------------------------------------------------
Deliberate, and ruled: step 4 is documentation, and the evaluator migration is
follow-up work tracked on #187.

It is not a frozen-core question — `evaluate.py` is not one of the five
(`CONTRIBUTING.md:46-54`). It is a *measurement* question. `evaluate.py`'s
`_resolve_principal` differs from `callosum.identity`'s in three ways that all bear on
what the eval measures:

  * it reads the two demoted columns rather than deriving from `membership.role`;
  * it has no `membership` JOIN, so the fail-closed property
    `test_no_membership_means_no_access_not_fallback_clearance` pins does not hold —
    a principal with no membership anywhere, or a revoked one, still resolves;
  * it takes `Principal.workspace_id`'s default (`retrieve.py:39`) and lands in the
    Default Workspace without naming it.

The consequence is that the eval's RBAC scoring — including the X1 negative case,
where a secret must never appear in an answer — grades the frozen gate against an
authorization model the product no longer uses. The two agree only by luck: #182
documents fifteen fixtures where `principal.role` and `principal.clearance` already
disagree, and `cli.py:126` seeds membership from both independently.

Changing `_resolve_principal` therefore changes what `eval-baseline-v3` measures, and
re-measuring a frozen baseline is a decision taken deliberately, not a side effect of
a documentation migration. **The comment says so, so that whoever next re-measures the
baseline is told by the schema itself, rather than having to find #187.**

--------------------------------------------------------------------------------
NO SCHEMA CHANGE, AND NOTHING REGENERATED
--------------------------------------------------------------------------------
One `COMMENT ON COLUMN`. No column added, dropped, retyped or constrained; no data
touched; no eval baseline regenerated or rewritten. `downgrade()` restores the absence
of a comment rather than inventing a previous text, because there was none —
`COMMENT ... IS NULL` is how Postgres spells "remove it".

Revision ID: 0030_document_principal_role
Revises: 0029_workspace_bootstrap
Create Date: 2026-09-04
"""
from alembic import op

revision = "0030_document_principal_role"
down_revision = "0029_workspace_bootstrap"
branch_labels = None
depends_on = None

_COMMENT = (
    "LEGACY / global metadata and bootstrap seed. Runtime authorization reads "
    "membership.role for the ACTIVE WORKSPACE, mapped to a clearance via "
    "callosum.identity.ROLE_TO_CLEARANCE (see callosum.identity.resolve_principal). "
    "Do not read this column to make an access decision: role is per-workspace, and "
    "the same person may be a founder in one workspace and an observer in another "
    "(#166). "
    "NOT UNUSED — two callers still read it. (1) callosum/cli.py seeds "
    "membership.role from this column at bootstrap; that is propagation, not an "
    "access decision. (2) callosum/evaluate.py resolves a Principal directly from "
    "this column and principal.clearance, with no membership join and no workspace "
    "scope: a LEGACY EVALUATION PATH, tracked in issue #187, which must be migrated "
    "to callosum.identity before the evaluation baseline is next re-measured "
    "deliberately — because migrating it changes what that baseline measures."
)


def upgrade() -> None:
    op.execute(f"COMMENT ON COLUMN principal.role IS '{_COMMENT}'")


def downgrade() -> None:
    # There was no comment before this migration — restore the absence, not an
    # invented previous text. `IS NULL` is how Postgres removes one.
    op.execute("COMMENT ON COLUMN principal.role IS NULL")
