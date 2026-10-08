"""Who may sign off a membership grant, pinned without a database (#225).

The behavioural tests for the approval gate live in
`tests/test_membership_approval.py` and are gated — they need Postgres, a real session
cookie, and a workspace. This file holds the two things that are *decisions* rather than
behaviours, and so belong in the fast tier where they are cheapest to catch:

  * the approver set is the two roles the maintainer named, and
  * the audit vocabulary the flow writes is registered.

Both are transcriptions. Neither is a place to silence a failure: if one of these fails,
something was widened, and the person who widened it has to change this file in the same
diff where a reviewer can see it.

---------------------------------------------------------------------------
WHY THIS FILE EXISTS SEPARATELY, WHICH IS ITSELF A FINDING
---------------------------------------------------------------------------
These three tests were originally written at the top of
`tests/test_membership_approval.py`, above its `CALLOSUM_RUN_INTEGRATION` guard, on the
assumption that code before a module-level skip still runs. **It does not.**
`pytest.skip(allow_module_level=True)` raises out of module *import*, so every test in
that file is skipped no matter where it is defined relative to the call — the three
"ungated" tests collected as zero tests and would have reported green forever without
executing.

That is the `COORDINATION.md` §5 failure shape ("a green test is not a passing test")
with a new mechanism, so it is written down here rather than quietly fixed: a DB-free
assertion placed in a gated file does not run. It needs its own ungated file.
"""

from __future__ import annotations

from meridian import audit, workspaces


def test_the_approver_roles_are_the_two_the_maintainer_named():
    """A transcription of #225, not a derivation from it.

    `founder` and `admin` are also the only two roles at clearance 4, so a
    clearance-threshold implementation would produce this same set *today* and diverge
    silently the first time another clearance-4 role is added.
    `identity.ROLE_TO_CLEARANCE`'s own comment states why that must not happen: "`admin`
    carries clearance 4 *and* separately carries membership-management authority — the
    two are distinct grants on one role."

    The same shape as `test_withheld_discipline.ERASES` and `0029`'s hardcoded founder
    clearance: a value that must match a ruling, pinned by a test that names the ruling.
    """
    assert workspaces._APPROVER_ROLES == frozenset({"founder", "admin"})


def test_the_approver_set_is_not_every_role_at_the_top_clearance():
    """States the coincidence explicitly, so the next reader does not have to notice it.

    This asserts the *equality that holds today* — approver set == roles at clearance 4 —
    and exists to be read, not to constrain: it is the reason the test above cannot be
    written as an inequality, and the reason the production constant is a literal. If a
    future role breaks this equality, this test fails and the failure is the notification
    that `_APPROVER_ROLES` now has to be re-examined on purpose rather than inherited.
    """
    from callosum import identity

    ceiling = max(identity.ROLE_TO_CLEARANCE.values())
    at_ceiling = {r for r, c in identity.ROLE_TO_CLEARANCE.items() if c == ceiling}
    assert at_ceiling == workspaces._APPROVER_ROLES, (
        "the approver set and the top clearance tier have diverged. That is allowed — "
        "they are different grants (#225) — but `_APPROVER_ROLES` must be re-read as a "
        "deliberate decision rather than left to coincide. Update this test and say which."
    )


def test_the_audit_vocabulary_the_approval_flow_writes_is_registered():
    """`record_audit_event` validates against these frozensets before it inserts.

    The SQL side is covered by `test_audit.py::test_the_sql_check_and_the_python_frozensets_agree`,
    which reads the CHECK back out of `pg_constraint` — that test is gated, so this one
    catches a Python-side omission without a database. Both halves matter: migration
    `0031` widens the constraint, and a value missing here would raise
    `AuditValidationError` and roll back an otherwise-correct approval.
    """
    assert "membership_request" in audit.AGGREGATE_TYPES
    assert {"approved", "rejected"} <= audit.ACTIONS
