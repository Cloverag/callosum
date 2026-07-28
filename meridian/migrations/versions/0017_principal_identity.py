"""principal_identity — external identity → principal (Meridian P3, CP-A/A1)

ADR-010. Maps an OIDC `(issuer, subject)` pair onto a `principal`, so an
authenticated caller can be resolved to someone this system knows about.

WHY A SEPARATE TABLE RATHER THAN A COLUMN ON `principal`:
  - one person can hold identities with more than one provider;
  - an identity can be revoked by deleting a row, without touching the person
    record that decisions, stances and commitments all reference;
  - `principal` is declared in the FROZEN `schema/postgres.sql`, and not
    reshaping it keeps that declaration honest.

WHY NOT MATCH ON EMAIL, WHICH IS ALREADY UNIQUE ON `principal`:
  email is mutable, it gets reassigned between people when someone leaves an
  organisation, and OIDC providers do not guarantee it. `(issuer, subject)` is
  stable and opaque, which is the only sound basis for deciding who someone is.

DELIBERATELY NOT TENANT-SCOPED, AND NO RLS.
  Identity is global — you are the same person in every workspace. `membership`
  is what scopes, and clearance is resolved from it (CP5b). Adding a
  `workspace_id` here would create a second place where "which tenant" is
  decided, which is the shape CP5b had to unwind for clearance.

  This also matters mechanically: login happens BEFORE a workspace is known, so
  this lookup cannot run through `store.pg(workspace_id)` at all. A tenant
  predicate on this table would have nothing to match against.

Revision ID: 0017_principal_identity
Revises: 0016_audit_event
Create Date: 2026-07-29
"""
from alembic import op

revision = "0017_principal_identity"
down_revision = "0016_audit_event"
branch_labels = None
depends_on = None

APP_ROLE = "callosum_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE principal_identity (
            id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

            -- CASCADE: an identity link to a deleted person is meaningless, and
            -- leaving orphans would let a recreated principal id silently inherit
            -- someone else's login. Principals are not deleted in normal operation;
            -- this is about not leaving a dangling credential if one ever is.
            principal_id  UUID NOT NULL REFERENCES principal(id) ON DELETE CASCADE,

            -- The OIDC issuer, verbatim. Stored as given rather than normalised:
            -- issuer URLs are compared exactly by the spec, and lower-casing one
            -- would make two distinct issuers collide in principle.
            provider      TEXT NOT NULL,

            -- The OIDC `sub` claim. Opaque, case-sensitive, and stable for the
            -- lifetime of the account — which is the whole reason it is the key.
            subject       TEXT NOT NULL,

            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT principal_identity_provider_not_empty
                CHECK (length(trim(provider)) > 0),
            CONSTRAINT principal_identity_subject_not_empty
                CHECK (length(trim(subject)) > 0),

            -- The lookup key. One external identity resolves to exactly one
            -- principal; a subject cannot be claimed twice.
            CONSTRAINT principal_identity_provider_subject_uq UNIQUE (provider, subject)
        )
        """
    )
    # Deliberately NO index on principal_id alone. The only query this table serves
    # is the exact (provider, subject) lookup above; "list this person's identities"
    # is an administrative question, not a request-path one, and an index would
    # invite it.

    # --- Privileges ---------------------------------------------------------
    #
    # `0004_app_role` sets ALTER DEFAULT PRIVILEGES granting SELECT, INSERT, UPDATE
    # and DELETE on every new table to callosum_app. That default has already
    # arrived by the time this runs, so the revoke below is LOAD-BEARING, not
    # decorative — without it the runtime role could mint its own identity links.
    # Same trap `0016_audit_event` had to handle for its append-only guarantee.
    #
    # The runtime needs exactly one thing: read a row to resolve a login.
    # Provisioning is an administrative act (ADR-011) and runs on the superuser
    # connection, which is why INSERT is not granted either.
    op.execute(f"REVOKE ALL ON principal_identity FROM {APP_ROLE}")
    op.execute(f"GRANT SELECT ON principal_identity TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS principal_identity")
