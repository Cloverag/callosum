"""Workspace bootstrap: the one path that may create a workspace (#166 step 5).

DECISION RECORD: issue #166 comment 5530505507 (the maintainer's ruling, transcribed
by the reviewing session). Read that first; this docstring summarises the SQL, not
the reasoning behind it.

--------------------------------------------------------------------------------
THE PROBLEM THIS CLOSES
--------------------------------------------------------------------------------
There was no workspace-creation path in production code. The only `INSERT INTO
workspace` outside a test fixture is `0001_workspace_and_membership.py:60`, seeding
the Default Workspace once, at bootstrap time. `POST /auth/workspace` only *selects*
an existing workspace (`meridian/api/auth.py:234`) and refuses without membership.
And the runtime role cannot write either table — `0011_control_plane_rls` revoked
INSERT/UPDATE/DELETE on both `membership` and `workspace`, and both carry FORCE ROW
LEVEL SECURITY, so even the table owner is subject to the policy unless the owning
role carries BYPASSRLS. `workspace`'s own predicate (`id = current_setting(...)`)
cannot be satisfied by a row that does not exist yet in any case.

--------------------------------------------------------------------------------
THE FUNCTION, AND THE ONE PROPERTY THE WHOLE DESIGN RESTS ON
--------------------------------------------------------------------------------
`create_workspace_with_founder(p_name, p_external_id, p_principal_id)` is
`SECURITY DEFINER`, owned by `callosum` (superuser, BYPASSRLS) — that ownership is
what lets it write past FORCE RLS and the revoked grants; a function owned by a
non-superuser could not. `search_path` is pinned to `public, pg_temp` so a caller
cannot redirect it by manipulating session state.

**It takes no workspace-id parameter.** It generates the id itself with
`uuid_generate_v4()`, the same default `workspace.id` already uses. That is the
security property, not an implementation detail: because the function names the
row it is about to create, it cannot be repurposed as "insert my membership into
workspace X" — it grants callers exactly one narrowly-scoped OPERATION (EXECUTE on
this function), never a PRIVILEGE (INSERT on either table). It also accepts no role
and no clearance argument — see below.

Both inserts (the workspace row and the founder's membership row) happen in one
PL/pgSQL function body, which is what makes the failure mode `tests/test_workspace_
bootstrap.py::test_a_failed_creation_leaves_no_orphan` proves possible: a single
statement in Postgres is atomic end-to-end unless the function itself catches its
own exception, and this one does not. A `p_principal_id` the `membership` foreign
key rejects aborts the whole call, workspace insert included — there is no
intermediate state where a workspace exists with no founder.

--------------------------------------------------------------------------------
THE CLEARANCE ARGUMENT THAT CANNOT BE TAKEN LITERALLY
--------------------------------------------------------------------------------
The maintainer's instruction was not to let this function accept an arbitrary
clearance argument, and to prefer that it derive the value from the authoritative
mapping (`callosum.identity.ROLE_TO_CLEARANCE`) instead. It cannot literally derive:
that mapping is a Python dict, and a SQL function cannot read it. Writing a SQL copy
of the mapping to derive from would be the exact duplication the instruction exists
to prevent, and verifying a passed-in value would need the same copy to check
against.

So the function takes neither a role nor a clearance argument at all — it hardcodes
`role = 'founder'` and clearance `4`. The number is not asserted safe by this
migration; it is asserted safe by `tests/test_workspace_bootstrap.py::
test_hardcoded_founder_clearance_matches_the_role_mapping`, which creates a real
workspace, reads the resulting membership row back FROM THE DATABASE, and compares
it against `identity.ROLE_TO_CLEARANCE["founder"]` — not against this migration's
source text. That is this codebase's own established idiom for two hand-maintained
values that must agree and have nothing forcing them to: see
`tests/test_audit.py::test_the_sql_check_and_the_python_frozensets_agree`, which
reads a CHECK constraint back from `pg_constraint` for the same reason. Duplication
is permitted here because a test asserts the agreement; it would not be permitted
if nothing did.

--------------------------------------------------------------------------------
NARROWING 0011 — MEMBERSHIP ONLY, AND WHY WORKSPACE IS UNTOUCHED
--------------------------------------------------------------------------------
`0011`'s reason for revoking INSERT/UPDATE/DELETE on `membership` was "neither table
has a runtime reader/writer". That premise is now false for `membership` — #166
exists specifically to make it false, so that a founder can grant, change and revoke
roles without a superuser in the loop. This migration grants back INSERT and UPDATE
only. Never DELETE: a revoked membership is `active = false`, not a removed row, the
same append-only discipline `board_members.py` and `documents.py` already use, and
for the same reason — a departed member's audit trail must stay resolvable.

`workspace` is NOT re-granted. Nothing in step 5 needs `callosum_app` to write it
directly: the one path that creates a row is the SECURITY DEFINER function, which
writes as its owner and does not consume the grant at all. `0011`'s argument for
`workspace` — administrative changes belong on the superuser path — still holds
exactly as written; only `membership`'s premise changed.

Revision ID: 0029_workspace_bootstrap
Revises: 0028_fix_clearance_comment
Create Date: 2026-09-04
"""
from alembic import op

revision = "0029_workspace_bootstrap"
down_revision = "0028_fix_clearance_comment"
branch_labels = None
depends_on = None

_FUNCTION = "create_workspace_with_founder(TEXT, TEXT, UUID)"

#: Hardcoded, deliberately — see the docstring above. Kept in step with
#: `callosum.identity.ROLE_TO_CLEARANCE["founder"]` by a test that reads this value
#: back from the database, not by import.
_FOUNDER_CLEARANCE = 4


def upgrade() -> None:
    op.execute(
        f"""
        CREATE FUNCTION create_workspace_with_founder(
            p_name TEXT,
            p_external_id TEXT,
            p_principal_id UUID
        ) RETURNS UUID
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
        DECLARE
            v_workspace_id UUID := uuid_generate_v4();
        BEGIN
            INSERT INTO workspace (id, name, external_id)
            VALUES (v_workspace_id, p_name, p_external_id);

            -- No ON CONFLICT: this row must be a genuine insert. A conflict here
            -- (the generated id already existing) is an actual anomaly and must
            -- abort loudly, not be silently absorbed into an existing membership.
            INSERT INTO membership (principal_id, workspace_id, role, clearance, active)
            VALUES (p_principal_id, v_workspace_id, 'founder', {_FOUNDER_CLEARANCE}, true);

            RETURN v_workspace_id;
        END;
        $$
        """
    )

    # Least privilege at the function itself, not only at the table: EXECUTE is not
    # granted to PUBLIC by default for a function owned by a non-invoking role in the
    # same way table grants work, but this is stated explicitly rather than relied on
    # implicitly — the same discipline `0011` used for the tables it touched.
    op.execute(f"REVOKE ALL ON FUNCTION {_FUNCTION} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_FUNCTION} TO callosum_app")

    # membership only. workspace stays fully revoked — see docstring.
    op.execute("GRANT INSERT, UPDATE ON membership TO callosum_app")


def downgrade() -> None:
    op.execute("REVOKE INSERT, UPDATE ON membership FROM callosum_app")
    op.execute(f"DROP FUNCTION IF EXISTS {_FUNCTION}")
