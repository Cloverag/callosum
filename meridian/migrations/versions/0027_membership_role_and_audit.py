"""membership.role CHECK, corrected vocabulary, and audit_event.aggregate_type += membership

Two unrelated constraints, landed together because both are prerequisites for #166's
membership-audit route (not yet built — this migration adds no route and no audit call).

--------------------------------------------------------------------------------
(a) + (b) — membership.role gets a CHECK, and the vocabulary comment is corrected
--------------------------------------------------------------------------------
`0001_workspace_and_membership.py:46` declares the column `TEXT NOT NULL` with a
comment listing six roles: `founder | admin | exec | director | observer | advisor`.
There has never been a CHECK — under the design this migration is a prerequisite for,
`membership.role` becomes a security-boundary key (P4 criterion 1, #166), and an
unconstrained key to a security lookup is exactly the failure mode that design was
chosen to avoid (see `docs/reviews/2026-09-03-p4-membership-decision-brief.md` §7).

`src/callosum/cli.py:86` seeds a role the `0001` comment never listed: `investor`
(`DEMO_PRINCIPALS`, Marcus Webb). The maintainer has ruled (`#166`, decision brief §11,
Q4) that `investor` is a real seventh role and the `0001` comment is the thing that's
wrong. `0001` has already run and cannot be edited — its comment is corrected here
instead, the same way `0023_audit_intake_refused` documents `0016`'s before/after sets
in the migration that changes them rather than in the frozen one.

The corrected seven, in the order the maintainer approved:

    founder | admin | exec | director | advisor | investor | observer

Checked against the live database before writing this CHECK, not assumed: the four
distinct `membership.role` values present today (`director`, `exec`, `founder`,
`investor`) are all inside this vocabulary. No backfill is required.

--------------------------------------------------------------------------------
(c) — audit_event.aggregate_type gains 'membership'
--------------------------------------------------------------------------------
`0016_audit_event.py:70` declares the CHECK inline, so Postgres auto-named the
constraint `audit_event_aggregate_type_check`. Recreated here under that same name,
per `0023`'s precedent, so the catalogue keeps one constraint on this column instead of
accumulating a second at every widening.

`meridian/audit.py:43` `AGGREGATE_TYPES` gains `"membership"` in the same commit as this
migration — `tests/test_audit.py::test_the_sql_check_and_the_python_frozensets_agree`
reads the constraint back from `pg_constraint` and asserts the Python frozenset and the
SQL CHECK agree, so changing one without the other fails, correctly.

This migration adds no route and no call to `record_audit_event` with
`aggregate_type="membership"` — there is nothing to audit yet. It only widens the
vocabulary so that work is not itself blocked on a migration later.

NAMED SHORTER THAN SPECIFIED, AND WHY
--------------------------------------
Originally `0027_membership_role_and_audit_aggregate` (40 chars). `alembic_version.
version_num` is `varchar(32)` — every existing revision id is under that (`0026_dedupe_
contradictory_fks` is 29), and this one silently wasn't. Found by running `alembic
upgrade head`, not by counting in advance: the ALTER TABLE statements succeeded, only
the `UPDATE alembic_version` failed, rolling the whole transaction back cleanly.
Shortened to `0027_membership_role_and_audit` (30 chars) rather than truncated further.

Revision ID: 0027_membership_role_and_audit
Revises: 0026_dedupe_contradictory_fks
Create Date: 2026-09-03
"""
from alembic import op

revision = "0027_membership_role_and_audit"
down_revision = "0026_dedupe_contradictory_fks"
branch_labels = None
depends_on = None

#: (a) — the corrected seven, maintainer-approved order (decision brief §11, Q4).
_ROLES = "('founder', 'admin', 'exec', 'director', 'advisor', 'investor', 'observer')"

#: (c) — the full set after this migration: the previous ten plus 'membership'.
#: Written out literally rather than imported from `meridian.audit.AGGREGATE_TYPES`,
#: per `0023`'s rule: a migration must describe the schema at the moment it ran, and
#: importing the live constant would make this file's meaning change every time that
#: set does.
_AGGREGATE_TYPES_AFTER = (
    "('meeting', 'agenda_item', 'document', 'decision', 'board_pack', 'minutes', "
    "'board_member', 'resolution', 'commitment', 'audit', 'membership')"
)
_AGGREGATE_TYPES_BEFORE = (
    "('meeting', 'agenda_item', 'document', 'decision', 'board_pack', 'minutes', "
    "'board_member', 'resolution', 'commitment', 'audit')"
)


def upgrade() -> None:
    op.execute(
        f"""
        ALTER TABLE membership
            ADD CONSTRAINT membership_role_check
                CHECK (role IN {_ROLES});
        """
    )
    op.execute(
        f"""
        ALTER TABLE audit_event
            DROP CONSTRAINT IF EXISTS audit_event_aggregate_type_check,
            ADD CONSTRAINT audit_event_aggregate_type_check
                CHECK (aggregate_type IN {_AGGREGATE_TYPES_AFTER});
        """
    )


def downgrade() -> None:
    # (a) — 0001 never had a CHECK on this column, so reversing is just dropping the
    # constraint this migration added. Unlike (c) below, narrowing a TEXT column back
    # to unconstrained can never violate existing rows, so there is nothing to delete
    # first.
    op.execute("ALTER TABLE membership DROP CONSTRAINT IF EXISTS membership_role_check")

    # (c) — same shape as 0023's downgrade, and the same reasoning transfers rather
    # than being copied blind: this migration is the ONLY place 'membership' enters
    # AGGREGATE_TYPES, and this branch adds no call to record_audit_event with that
    # aggregate_type (no route exists yet) — so no row predating this migration can
    # carry the value, and none this branch's own code creates either. A row could
    # only exist here if something else writing to this shared database inserted one
    # between upgrade and downgrade; deleting it is the same trade 0023 made: an
    # append-only trail loses rows only of a value that could not have existed before
    # the migration that introduced it.
    op.execute("DELETE FROM audit_event WHERE aggregate_type = 'membership'")
    op.execute(
        f"""
        ALTER TABLE audit_event
            DROP CONSTRAINT IF EXISTS audit_event_aggregate_type_check,
            ADD CONSTRAINT audit_event_aggregate_type_check
                CHECK (aggregate_type IN {_AGGREGATE_TYPES_BEFORE});
        """
    )
