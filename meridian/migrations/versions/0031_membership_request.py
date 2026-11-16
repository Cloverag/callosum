"""Pending membership grants, awaiting a founder/admin approval (#225).

DECISION RECORD: issue #225 — the maintainer's requirement, added while signing the P4
exit gate (#224, 2026-10-08): *"investors adding investors is fine but also need
permission from another person like manager of this workspace."* Clarified in the same
session: the approver is an active `founder` or `admin` in the same workspace, founders
and admins grant directly, and every other role's grant does not take effect until an
approver signs it.

--------------------------------------------------------------------------------
WHY A SEPARATE TABLE, AND NOT A `pending` STATE ON `membership`
--------------------------------------------------------------------------------
#225 sketched "a pending membership state that `identity.resolve_*` ignores". That shape
was examined and rejected, for a reason that only shows up once you write out what a
grant actually does: `grant_membership()` is an **upsert** on `(principal_id,
workspace_id)`. It changes an existing member's role as readily as it adds a new one.

So a pending state living on the `membership` row has to be written onto the row that is
already there — and whatever value makes `identity.resolve_*` ignore it would deactivate
a member who is currently active. That turns the grant route into a denial-of-service:
anti-escalation only checks the role being *requested* against the actor's clearance, so
an investor (clearance 1) may legitimately request `observer` (0) for anybody — including
an active founder. Under the sketched shape, submitting that request would suspend the
founder until somebody approved or rejected it. The approval requirement, which exists to
*narrow* what a non-admin can do, would have handed them a new weapon.

A request that lives in its own table cannot do that. `membership` is not touched until an
approver signs, so:

  * **Pending is not a membership at all**, which is a stronger guarantee than "pending is
    a membership that readers filter out". `identity.resolve_*` needs no change
    whatsoever — there is no new state for a future edit to forget to exclude. The one
    query that decides who you are (`_PRINCIPAL_WITH_ACTIVE_MEMBERSHIP`) is untouched by
    this migration, and that is the security property, not a convenience.
  * An active member's access is unaffected by anyone filing a request about them.
  * The queue is readable as a queue — who asked, for whom, when — which an in-place
    column could not express without a second table anyway.

--------------------------------------------------------------------------------
NO DEFAULT ON `workspace_id` (#196)
--------------------------------------------------------------------------------
Every table from `0005` through `0025` declares `workspace_id UUID NOT NULL DEFAULT
'00000000-0000-0000-0000-000000000001'`. #196 is open against exactly that pattern: a
default silently makes an omitted tenant into the default tenant, which under FORCE RLS
shows up as a row that vanishes rather than an error that names the bug. This table takes
no default. A caller that does not say which workspace gets a NOT NULL violation, which is
the outcome #196 asks for.

--------------------------------------------------------------------------------
THE PARTIAL UNIQUE INDEX IS WHAT MAKES `reject` LOAD-BEARING
--------------------------------------------------------------------------------
`uq_membership_request_pending` allows at most one *pending* request per
(workspace, principal). Without it, a non-admin could file the same request a thousand
times and the approver's queue becomes unusable; with it, the second attempt is refused by
the database rather than by a read-then-insert that races.

It also forces a design consequence worth naming here rather than discovering later: once
a pending row blocks further requests for that principal, there must be a way to clear one
without approving it. That is why `reject_membership_request()` exists — not as a courtesy
to the UI, but because a queue with no exit would wedge the grant path permanently for any
principal who ever had a request filed about them.

--------------------------------------------------------------------------------
AUDIT VOCABULARY
--------------------------------------------------------------------------------
One new `aggregate_type` (`membership_request`) and two new actions (`approved`,
`rejected`). `created` is reused for the filing of a request — with
`aggregate_type = 'membership_request'` it already reads correctly, and inventing a
`membership_requested` action would duplicate in the action what the aggregate type
already says.

The actions are deliberately generic rather than membership-specific: `approved` and
`rejected` are what happens to a request, and `aggregate_type` says which kind. The
`proposed_change` queue is the obvious future second user.

Both lists are written out literally rather than imported from `meridian.audit`, per
`0023`'s rule: a migration describes the schema at the moment it ran, and importing the
live constant would make this file's meaning change every time that set does.
`tests/test_audit.py::test_the_sql_check_and_the_python_frozensets_agree` is what keeps
the two in step — it reads the constraint back out of `pg_constraint` and compares.

Revision ID: 0031_membership_request
Revises: 0030_document_principal_role
Create Date: 2026-10-08
"""
from alembic import op

revision = "0031_membership_request"
down_revision = "0030_document_principal_role"
branch_labels = None
depends_on = None

_PREDICATE = "workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid"

#: The canonical seven, mirroring `0027`'s `membership_role_check`. A request that could
#: never become a membership is not worth storing, so the same vocabulary is constrained
#: on the way in.
_ROLES = "('founder', 'admin', 'exec', 'director', 'advisor', 'investor', 'observer')"

_STATUSES = "('pending', 'approved', 'rejected')"

_AGGREGATE_TYPES_AFTER = (
    "('meeting', 'agenda_item', 'document', 'decision', 'board_pack', 'minutes', "
    "'board_member', 'resolution', 'commitment', 'audit', 'membership', "
    "'membership_request')"
)
_AGGREGATE_TYPES_BEFORE = (
    "('meeting', 'agenda_item', 'document', 'decision', 'board_pack', 'minutes', "
    "'board_member', 'resolution', 'commitment', 'audit', 'membership')"
)

_ACTIONS_AFTER = (
    "('created', 'updated', 'status_changed', 'superseded', 'published', 'deleted', "
    "'voted', 'reordered', 'item_added', 'item_removed', 'recorded', "
    "'intake_duplicate_refused', 'approved', 'rejected')"
)
_ACTIONS_BEFORE = (
    "('created', 'updated', 'status_changed', 'superseded', 'published', 'deleted', "
    "'voted', 'reordered', 'item_added', 'item_removed', 'recorded', "
    "'intake_duplicate_refused')"
)


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE membership_request (
            id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

            -- No DEFAULT, deliberately — see the docstring above (#196).
            workspace_id   UUID NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,

            -- Who the membership would be for. CASCADE, matching `membership`'s own FK
            -- on the same column: if the person is gone, a request to give them a role
            -- is moot and keeping it would reference nobody.
            principal_id   UUID NOT NULL REFERENCES principal(id) ON DELETE CASCADE,
            role           TEXT NOT NULL,

            -- Who asked. NOT NULL and never defaulted: a request with no requester
            -- cannot be re-validated at approval time, and re-validating the requester's
            -- standing is what stops a pending request outliving the authority that
            -- filed it (see `workspaces.approve_membership_request`).
            --
            -- NO ON DELETE, unlike `principal_id` above — deliberately asymmetric. The
            -- two columns fail in opposite directions: losing the target makes the row
            -- meaningless, while losing the requester makes it unaccountable. RESTRICT
            -- (the default) means a principal who has ever filed a request cannot be
            -- deleted out from under the record of it; the deletion fails loudly instead
            -- of quietly erasing who proposed whom.
            requested_by   UUID NOT NULL REFERENCES principal(id),

            status         TEXT NOT NULL DEFAULT 'pending',

            -- Who signed, and when. Null while pending; the CHECK below makes that
            -- the only shape the two can take.
            decided_by     UUID REFERENCES principal(id),
            decided_at     TIMESTAMPTZ,

            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT membership_request_role_check
                CHECK (role IN {_ROLES}),
            CONSTRAINT membership_request_status_check
                CHECK (status IN {_STATUSES}),

            -- A decision is three facts written together or none of them. Without this a
            -- row could read 'approved' with no signer, which is precisely the
            -- attribution gap the approval requirement exists to close — an approved
            -- grant whose audit trail cannot name who approved it is no better than the
            -- unapproved grant it replaced.
            CONSTRAINT membership_request_decided_together
                CHECK (
                    (status = 'pending'  AND decided_by IS NULL     AND decided_at IS NULL)
                 OR (status <> 'pending' AND decided_by IS NOT NULL AND decided_at IS NOT NULL)
                )
        )
        """
    )

    # At most one OPEN request per principal per workspace. Decided rows are exempt, so
    # the history of what was asked and answered is kept in full — this bounds the queue,
    # it does not prune it.
    op.execute(
        "CREATE UNIQUE INDEX uq_membership_request_pending "
        "ON membership_request (workspace_id, principal_id) WHERE status = 'pending'"
    )
    # The read path is "what is waiting for me to sign", oldest first.
    op.execute(
        "CREATE INDEX ix_membership_request_queue "
        "ON membership_request (workspace_id, status, created_at)"
    )

    op.execute("ALTER TABLE membership_request ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE membership_request FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON membership_request
            FOR ALL
            USING ({_PREDICATE})
            WITH CHECK ({_PREDICATE})
        """
    )
    # SELECT, INSERT, UPDATE — never DELETE. A decided request is kept, the same
    # append-only discipline `membership` itself follows (`0029`: "a revoked membership is
    # `active = false`, not a removed row"). Who asked for what, and who refused it, has
    # to stay resolvable after the fact.
    op.execute("GRANT SELECT, INSERT, UPDATE ON membership_request TO callosum_app")

    op.execute(
        f"""
        ALTER TABLE audit_event
            DROP CONSTRAINT IF EXISTS audit_event_aggregate_type_check,
            ADD CONSTRAINT audit_event_aggregate_type_check
                CHECK (aggregate_type IN {_AGGREGATE_TYPES_AFTER});
        """
    )
    op.execute(
        f"""
        ALTER TABLE audit_event
            DROP CONSTRAINT IF EXISTS audit_event_action_check,
            ADD CONSTRAINT audit_event_action_check
                CHECK (action IN {_ACTIONS_AFTER});
        """
    )


def downgrade() -> None:
    # Rows carrying the new vocabulary violate the narrower constraints, so they go
    # first. The same trade `0023` and `0027` made, and acceptable for the same reason:
    # neither the aggregate type nor the two actions existed before this migration, so
    # nothing predating it can be lost. Deleting by aggregate_type AND by action, because
    # the grant this flow writes carries `aggregate_type = 'membership'` with a reused
    # action — that row predates nothing and must survive the downgrade, which is why the
    # first statement is scoped to the new aggregate type rather than to the flow.
    op.execute("DELETE FROM audit_event WHERE aggregate_type = 'membership_request'")
    op.execute("DELETE FROM audit_event WHERE action IN ('approved', 'rejected')")
    op.execute(
        f"""
        ALTER TABLE audit_event
            DROP CONSTRAINT IF EXISTS audit_event_action_check,
            ADD CONSTRAINT audit_event_action_check
                CHECK (action IN {_ACTIONS_BEFORE});
        """
    )
    op.execute(
        f"""
        ALTER TABLE audit_event
            DROP CONSTRAINT IF EXISTS audit_event_aggregate_type_check,
            ADD CONSTRAINT audit_event_aggregate_type_check
                CHECK (aggregate_type IN {_AGGREGATE_TYPES_BEFORE});
        """
    )

    op.execute("DROP POLICY IF EXISTS tenant_isolation ON membership_request")
    op.execute("DROP TABLE IF EXISTS membership_request")
