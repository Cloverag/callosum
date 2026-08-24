"""widen audit_event.action for intake_duplicate_refused (ADR-016)

`meridian/audit.py`'s `ACTIONS` frozenset and the SQL `CHECK` on `audit_event.action`
are maintained in two files, and `tests/test_audit.py::
test_the_sql_check_and_the_python_frozensets_agree` reads the constraint back from
`pg_constraint` to keep them honest. Adding the action in Python alone left the two
disagreeing, and that test failed — correctly, and before the code reached anyone.

Worth recording *how* it failed, because the failure mode was the designed one: the
insert violated the CHECK, `_record_duplicate_refusal` logged it and swallowed it as
intended, and the caller still received the correct `409`. The audit trail was the only
casualty, which is exactly the trade the helper's docstring commits to.

The constraint is declared inline in `0016_audit_event`, so Postgres auto-named it
`audit_event_action_check`. It is recreated here with that same name rather than a new
one, so the catalogue keeps one constraint on this column rather than accumulating a
second with a different name at every widening.

Revision ID: 0023_audit_intake_refused
Revises: 0022_doc_content_hash_uq
Create Date: 2026-08-22
"""
from alembic import op

revision = "0023_audit_intake_refused"
down_revision = "0022_doc_content_hash_uq"
branch_labels = None
depends_on = None

#: The full set after this migration — the previous eleven plus one. Written out rather
#: than derived from `meridian.audit.ACTIONS`: a migration must describe the schema at
#: the moment it ran, and importing the live constant would make this file's meaning
#: change every time that set does.
_ACTIONS_AFTER = (
    "('created', 'updated', 'status_changed', 'superseded', 'published', 'deleted', "
    "'voted', 'reordered', 'item_added', 'item_removed', 'recorded', "
    "'intake_duplicate_refused')"
)

_ACTIONS_BEFORE = (
    "('created', 'updated', 'status_changed', 'superseded', 'published', 'deleted', "
    "'voted', 'reordered', 'item_added', 'item_removed', 'recorded')"
)


def upgrade() -> None:
    op.execute(
        f"""
        ALTER TABLE audit_event
            DROP CONSTRAINT IF EXISTS audit_event_action_check,
            ADD CONSTRAINT audit_event_action_check
                CHECK (action IN {_ACTIONS_AFTER});
        """
    )


def downgrade() -> None:
    # Rows carrying the new action would violate the narrower constraint, so they are
    # removed first. That is a deletion from an append-only trail and is only acceptable
    # because the action did not exist before this migration: nothing predating it can be
    # lost, and leaving them would make the downgrade fail rather than reverse.
    op.execute("DELETE FROM audit_event WHERE action = 'intake_duplicate_refused'")
    op.execute(
        f"""
        ALTER TABLE audit_event
            DROP CONSTRAINT IF EXISTS audit_event_action_check,
            ADD CONSTRAINT audit_event_action_check
                CHECK (action IN {_ACTIONS_BEFORE});
        """
    )
