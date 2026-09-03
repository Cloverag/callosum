"""Clearance resolves through membership, and `principal` is workspace-scoped (CP5b).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

P1 moved clearance from the global `principal.clearance` column onto a
per-workspace `membership` row, and the runtime never adopted it — every caller
lookup read the global column and `membership` sat empty with no readers. These
tests pin the corrected behaviour, and the fail-closed cases matter more than the
happy path: this is the input to the frozen RBAC gate in `retrieve.py`.
"""

import os
import uuid

import pytest

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip("set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests", allow_module_level=True)

import psycopg

from callosum import store
from callosum.config import settings
from callosum.identity import (
    IdentityNotProvisioned,
    PrincipalNotFound,
    resolve_identity,
    resolve_principal_by_subject,
    resolve_principal,
    resolve_principal_by_id,
    resolve_principal_id,
)

pytestmark = pytest.mark.integration


def _admin(sql: str, params: tuple = ()) -> None:
    with psycopg.connect(settings().postgres_dsn) as conn:
        conn.execute(sql, params)
        conn.commit()


def _workspace() -> str:
    ws = str(uuid.uuid4())
    _admin(
        "INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s)",
        (ws, f"id-{ws[:8]}", ws),
    )
    return ws


def _person(name: str, *, role: str = "founder", legacy_clearance: int = 4) -> str:
    pid = str(uuid.uuid4())
    _admin(
        "INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, %s, %s)",
        (pid, name, role, legacy_clearance),
    )
    return pid


def _member(
    principal_id: str,
    workspace_id: str,
    clearance: int,
    *,
    role: str = "founder",
    active: bool = True,
) -> None:
    """`clearance` is the STORED value only — #166 made it a non-authoritative
    column (see `identity.ROLE_TO_CLEARANCE`). Most callers below still pass a
    `clearance` that happens to equal the effective one for `role='founder'` (4),
    which is what makes them pass without meaning to assert anything about the
    stored column. The ones that don't are the tests that actually exercise it.
    """
    _admin(
        "INSERT INTO membership (principal_id, workspace_id, role, clearance, active)"
        " VALUES (%s, %s, %s, %s, %s)",
        (principal_id, workspace_id, role, clearance, active),
    )


def _cleanup(principal_ids: list[str], workspace_ids: list[str]) -> None:
    for ws in workspace_ids:
        # Before every other delete below. `audit_event.workspace_id` is ON DELETE
        # RESTRICT (0016, deliberately), so once any route in this file is audited the
        # workspace cannot be dropped until its trail is.
        #
        # Scoped by workspace only. `audit_event.actor_principal_id` is RESTRICT too,
        # and the `principal` deletes below are NOT covered by this line — they are
        # safe because no test here references DEFAULT_WORKSPACE_ID, so every principal
        # it creates acts only inside a workspace it also creates. That is a property
        # of how these tests are built, not of the FK. A test that has a principal act
        # outside `workspace_ids` needs the actor-scoped delete that
        # `test_auth_session.py` and `test_principal_identity.py` use. Issue #170.
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM membership WHERE workspace_id = %s", (ws,))
    for pid in principal_ids:
        _admin("DELETE FROM principal WHERE id = %s", (pid,))
    for ws in workspace_ids:
        _admin("DELETE FROM workspace WHERE id = %s", (ws,))


def test_clearance_comes_from_the_role_mapping_not_either_stored_column():
    """Two supersessions, both pinned by one fixture with three disagreeing values.

    Originally asserted `p.clearance == 1` (the stored `membership.clearance`),
    proving clearance no longer read the legacy global `principal.clearance` (4).
    That design was itself superseded by #166: `membership.clearance` stopped
    being an authorization source too, for the same class of reason — nothing
    forced it to agree with `membership.role`, and `cli.py`'s single-INSERT
    seeding made that agreement look tested when it was only ever a coincidence
    of how the fixture was built (`docs/reviews/2026-09-03-p4-membership-
    decision-brief.md` §3, §12.3).

    All three values are made to disagree on purpose: legacy `principal.clearance`
    4, stored `membership.clearance` 1, role `director` mapping to 3. Only the
    role mapping winning proves this — seeding any two alike would let a resolver
    reading the wrong column pass by accident.
    """
    ws = _workspace()
    pid = _person("Divergent Director", legacy_clearance=4)
    _member(pid, ws, clearance=1, role="director")
    try:
        with store.pg(ws) as conn:
            p = resolve_principal(conn, "Divergent", workspace_id=ws)
            assert p.clearance == 3, "resolver did not read the role->clearance mapping"
            assert p.role == "director"
            assert p.workspace_id == ws
    finally:
        _cleanup([pid], [ws])


def test_changing_the_membership_role_changes_effective_clearance():
    """The direct claim #166 makes: role drives clearance, not the other way round.

    Same principal, same workspace, same stored `membership.clearance` throughout
    (2, chosen to disagree with every mapped value below) — only `role` changes
    between resolutions, and clearance tracks it every time. This is the test the
    ruling asked for by name: "changing `membership.role` changes effective
    clearance."
    """
    ws = _workspace()
    pid = _person("Promoted Observer")
    try:
        for role, expected in (
            ("observer", 0),
            ("advisor", 2),
            ("director", 3),
            ("founder", 4),
        ):
            _admin("DELETE FROM membership WHERE principal_id = %s", (pid,))
            _member(pid, ws, clearance=2, role=role)
            with store.pg(ws) as conn:
                p = resolve_principal_by_id(conn, pid, workspace_id=ws)
            assert p.clearance == expected, f"role={role!r} should map to {expected}"
    finally:
        _cleanup([pid], [ws])


def test_an_unrecognised_stored_role_fails_closed_not_open():
    """`ROLE_TO_CLEARANCE` cannot cover a value it does not know about — this
    branch carries no CHECK on `membership.role` (that is `0027`, a separate,
    not-yet-merged branch), so the database will currently accept anything.

    A bare `KeyError` would be a crash a caller has to know to catch; silently
    defaulting to clearance 0 would be a fail-*open* shape disguised as fail-closed
    (an unrecognised role still resolving, just quietly). Neither is what
    `_clearance_for` does — it raises `PrincipalNotFound`, the same refusal an
    absent membership produces, so an unrecognised role is indistinguishable from
    "not resolvable" rather than partially trusted.
    """
    ws = _workspace()
    pid = _person("Undefined Role Holder")
    _member(pid, ws, clearance=4, role="mythical_role")
    try:
        with store.pg(ws) as conn:
            with pytest.raises(PrincipalNotFound):
                resolve_principal_by_id(conn, pid, workspace_id=ws)
    finally:
        _cleanup([pid], [ws])


def test_no_membership_means_no_access_not_fallback_clearance():
    """A principal without a membership here does not resolve at all.

    Fail-closed: they are granted neither their global clearance nor clearance 0.
    A fallback would silently re-open the cross-tenant path this replaced.
    """
    home, elsewhere = _workspace(), _workspace()
    pid = _person("Homebound Founder", legacy_clearance=4)
    _member(pid, home, clearance=4)
    try:
        with store.pg(home) as conn:
            assert resolve_principal(conn, "Homebound", workspace_id=home).clearance == 4

        with store.pg(elsewhere) as conn:
            with pytest.raises(PrincipalNotFound):
                resolve_principal(conn, "Homebound", workspace_id=elsewhere)
    finally:
        _cleanup([pid], [home, elsewhere])


def test_inactive_membership_does_not_resolve():
    """Revoking access means deactivating the membership, and it must take effect."""
    ws = _workspace()
    pid = _person("Departed Director")
    _member(pid, ws, clearance=4, active=False)
    try:
        with store.pg(ws) as conn:
            with pytest.raises(PrincipalNotFound):
                resolve_principal(conn, "Departed", workspace_id=ws)
    finally:
        _cleanup([pid], [ws])


def test_principal_rows_are_invisible_from_another_workspace():
    """`principal` itself is now RLS-scoped through membership (0013).

    Closes the residual gap left by `p1.0.5`, which could not apply this policy
    while `membership` was empty.
    """
    home, elsewhere = _workspace(), _workspace()
    pid = _person("Scoped Person")
    _member(pid, home, clearance=3)
    try:
        with store.pg(home) as conn:
            assert conn.execute(
                "SELECT count(*) AS n FROM principal WHERE id = %s", (uuid.UUID(pid),)
            ).fetchone()["n"] == 1

        with store.pg(elsewhere) as conn:
            assert conn.execute(
                "SELECT count(*) AS n FROM principal WHERE id = %s", (uuid.UUID(pid),)
            ).fetchone()["n"] == 0, "principal leaked across workspaces"
    finally:
        _cleanup([pid], [home, elsewhere])


def test_runtime_role_cannot_create_people():
    """Identity creation is administrative; `callosum init` moved to the admin path."""
    ws = _workspace()
    try:
        with store.pg(ws) as conn:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(
                    "INSERT INTO principal (name, role, clearance) VALUES ('Intruder', 'founder', 4)"
                )
    finally:
        _cleanup([], [ws])


def test_reviewer_id_resolution_is_also_membership_scoped():
    """Attribution lookups are scoped too, so a foreign name cannot be recorded here."""
    home, elsewhere = _workspace(), _workspace()
    pid = _person("Reviewer Person")
    _member(pid, home, clearance=2)
    try:
        with store.pg(home) as conn:
            assert str(resolve_principal_id(conn, "Reviewer", workspace_id=home)) == pid
        with store.pg(elsewhere) as conn:
            assert resolve_principal_id(conn, "Reviewer", workspace_id=elsewhere) is None
    finally:
        _cleanup([pid], [home, elsewhere])


# ---------------------------------------------------------------------------
# resolve_principal_by_id — the lookup an authenticated request should use (P3 §5.2)
#
# resolve_principal() matches on `name ILIKE '%fragment%'` and takes the first
# alphabetical hit. That is fine when a human types their own name into a CLI and
# unacceptable as an authentication path. These pin the exact-identifier behaviour.
# ---------------------------------------------------------------------------

def test_by_id_resolves_clearance_from_the_role_mapping_not_either_stored_column():
    """Same three-way disagreement fixture as the name-based test, same reason.

    See `test_clearance_comes_from_the_role_mapping_not_either_stored_column` —
    this pins the identical property through `resolve_principal_by_id` instead of
    `resolve_principal`, since the two do not share an implementation past the
    common JOIN.
    """
    ws = _workspace()
    pid = _person("Exact Match Director", legacy_clearance=4)
    _member(pid, ws, clearance=1, role="director")
    try:
        with store.pg(ws) as conn:
            p = resolve_principal_by_id(conn, pid, workspace_id=ws)
            assert p.clearance == 3, "did not read the role->clearance mapping"
            assert p.role == "director"
            assert str(p.id) == pid
            assert p.workspace_id == ws
    finally:
        _cleanup([pid], [ws])


def test_by_id_accepts_a_uuid_object_as_well_as_a_string():
    ws = _workspace()
    pid = _person("Uuid Form Director")
    _member(pid, ws, clearance=2, role="observer")
    try:
        with store.pg(ws) as conn:
            # clearance=2 is the stored value and irrelevant (#166) — 'observer' maps
            # to 0. Asserting 0 here is what makes this test still mean something
            # rather than merely happening to pass at the coincidental default (4).
            assert resolve_principal_by_id(conn, uuid.UUID(pid), workspace_id=ws).clearance == 0
    finally:
        _cleanup([pid], [ws])


def test_by_id_fails_closed_without_a_membership():
    """A real principal, a real workspace, and no membership between them."""
    ws = _workspace()
    pid = _person("Stranger Here")
    try:
        with store.pg(ws) as conn:
            with pytest.raises(PrincipalNotFound):
                resolve_principal_by_id(conn, pid, workspace_id=ws)
    finally:
        _cleanup([pid], [ws])


def test_by_id_fails_closed_on_a_deactivated_membership():
    ws = _workspace()
    pid = _person("Departed Director")
    _member(pid, ws, clearance=3, active=False)
    try:
        with store.pg(ws) as conn:
            with pytest.raises(PrincipalNotFound):
                resolve_principal_by_id(conn, pid, workspace_id=ws)
    finally:
        _cleanup([pid], [ws])


def test_by_id_does_not_resolve_across_workspaces():
    """The membership is in B; the lookup is in A. The id alone must not be enough."""
    ws_a, ws_b = _workspace(), _workspace()
    pid = _person("Member Of B Only")
    _member(pid, ws_b, clearance=4)
    try:
        with store.pg(ws_a) as conn:
            with pytest.raises(PrincipalNotFound):
                resolve_principal_by_id(conn, pid, workspace_id=ws_a)
        # ...and resolves normally in the workspace they actually belong to.
        with store.pg(ws_b) as conn:
            assert resolve_principal_by_id(conn, pid, workspace_id=ws_b).clearance == 4
    finally:
        _cleanup([pid], [ws_a, ws_b])


def test_by_id_gives_one_answer_for_unknown_absent_and_malformed():
    """No membership oracle, and no distinguishable error for a malformed id either.

    A caller learning "that id was invalid" versus "that id was not found" learns
    nothing useful, and two error shapes are two things to reason about.
    """
    ws = _workspace()
    try:
        with store.pg(ws) as conn:
            for bad in (str(uuid.uuid4()), "not-a-uuid", "", None, 12345):
                with pytest.raises(PrincipalNotFound):
                    resolve_principal_by_id(conn, bad, workspace_id=ws)
    finally:
        _cleanup([], [ws])


def test_by_id_is_exact_where_the_name_lookup_is_fuzzy():
    """The defect that makes the name lookup unusable for authentication.

    Two principals whose names share a substring: `resolve_principal("An")` returns
    whichever sorts first, so it can hand back the WRONG person. By id, each resolves
    to themselves.
    """
    ws = _workspace()
    anna = _person("Anna Fischer")
    joanna = _person("Joanna Fischer")
    # Distinguished by role, not by the now-inert stored clearance (#166) — both
    # get clearance=4 stored, so a resolver that fell back to the stored column
    # would pass this test by accident. 'observer' vs 'founder' is the only thing
    # that actually gives them different effective clearance.
    _member(anna, ws, clearance=4, role="observer")
    _member(joanna, ws, clearance=4, role="founder")
    try:
        with store.pg(ws) as conn:
            # The fuzzy lookup collapses both onto one arbitrary winner...
            fuzzy = resolve_principal(conn, "anna", workspace_id=ws)
            assert str(fuzzy.id) in (anna, joanna)

            # ...while the exact lookup cannot confuse them, and — the part that
            # matters — cannot hand the low-clearance reader the high clearance.
            assert resolve_principal_by_id(conn, anna, workspace_id=ws).clearance == 0
            assert resolve_principal_by_id(conn, joanna, workspace_id=ws).clearance == 4
    finally:
        _cleanup([anna, joanna], [ws])


def test_by_id_requires_an_explicit_workspace():
    """No default. An authenticated request always knows its workspace, and
    defaulting one would reintroduce the fail-open behaviour meridian.tenancy
    exists to prevent."""
    import inspect

    sig = inspect.signature(resolve_principal_by_id)
    assert sig.parameters["workspace_id"].default is inspect.Parameter.empty


# ---------------------------------------------------------------------------
# resolve_identity / resolve_principal_by_subject — CP-A/A2 (ADR-010, ADR-011)
#
# Authentication is two halves. `resolve_identity` maps an OIDC (issuer, subject)
# onto a principal and takes NO workspace, because login happens before one is
# chosen. `resolve_principal_by_id` applies the membership rule once it is. Keeping
# them separate is what makes identity global and authorization per-tenant.
# ---------------------------------------------------------------------------

PROVIDER = "https://idp.example/"


def _identity(principal_id: str, subject: str, provider: str = PROVIDER) -> None:
    _admin(
        "INSERT INTO principal_identity (principal_id, provider, subject) VALUES (%s, %s, %s)",
        (principal_id, provider, subject),
    )


def test_resolve_identity_maps_a_subject_to_a_principal():
    ws = _workspace()
    pid = _person("Subject Holder")
    _member(pid, ws, clearance=2)
    subject = f"sub-{uuid.uuid4()}"
    _identity(pid, subject)
    try:
        with store.pg(ws) as conn:
            assert str(resolve_identity(conn, PROVIDER, subject)) == pid
    finally:
        _cleanup([pid], [ws])


def test_resolve_identity_takes_no_workspace():
    """Login happens before a workspace is selected.

    A workspace parameter here would have nothing to match against — and
    `principal_identity` has no tenant column precisely so it cannot acquire one.
    """
    import inspect

    assert "workspace_id" not in inspect.signature(resolve_identity).parameters


def test_an_unprovisioned_subject_is_rejected_not_created():
    """ADR-011: provisioning is an administrative act.

    The identity provider will happily authenticate a stranger; that must not be
    enough to create a principal.
    """
    ws = _workspace()
    try:
        with store.pg(ws) as conn:
            before = conn.execute("SELECT count(*) AS n FROM principal_identity").fetchone()["n"]
            with pytest.raises(IdentityNotProvisioned):
                resolve_identity(conn, PROVIDER, f"stranger-{uuid.uuid4()}")
            after = conn.execute("SELECT count(*) AS n FROM principal_identity").fetchone()["n"]
        assert before == after, "a failed login must not provision anything"
    finally:
        _cleanup([], [ws])


def test_IdentityNotProvisioned_is_still_caught_as_PrincipalNotFound():
    """Subclassing matters: a caller that does not care about the distinction must
    not accidentally let this one through."""
    assert issubclass(IdentityNotProvisioned, PrincipalNotFound)

    ws = _workspace()
    try:
        with store.pg(ws) as conn:
            with pytest.raises(PrincipalNotFound):
                resolve_identity(conn, PROVIDER, f"stranger-{uuid.uuid4()}")
    finally:
        _cleanup([], [ws])


def test_the_subject_is_not_echoed_in_the_error():
    # It is the caller's own identifier so this is not a leak, but exception messages
    # end up in logs and an external identifier should not be scattered through them.
    ws = _workspace()
    subject = f"secret-subject-{uuid.uuid4()}"
    try:
        with store.pg(ws) as conn:
            with pytest.raises(IdentityNotProvisioned) as caught:
                resolve_identity(conn, PROVIDER, subject)
        assert subject not in str(caught.value)
    finally:
        _cleanup([], [ws])


@pytest.mark.parametrize("provider,subject", [("", "s"), ("   ", "s"), (PROVIDER, ""), (PROVIDER, "  ")])
def test_empty_credentials_are_refused_without_a_query(provider, subject):
    ws = _workspace()
    try:
        with store.pg(ws) as conn:
            with pytest.raises(IdentityNotProvisioned):
                resolve_identity(conn, provider, subject)
    finally:
        _cleanup([], [ws])


def test_matching_is_exact_and_case_sensitive():
    """Subjects are opaque and issuers compare verbatim.

    Normalising either would risk collapsing two distinct identities into one — the
    reverse of the fuzzy-name defect that made `resolve_principal` unusable for auth.
    """
    ws = _workspace()
    pid = _person("Exact Subject")
    _member(pid, ws, clearance=2)
    subject = f"Sub-MixedCase-{uuid.uuid4()}"
    _identity(pid, subject)
    try:
        with store.pg(ws) as conn:
            assert str(resolve_identity(conn, PROVIDER, subject)) == pid
            for wrong in (subject.lower(), subject.upper(), f" {subject}"):
                with pytest.raises(IdentityNotProvisioned):
                    resolve_identity(conn, PROVIDER, wrong)
            # Right subject, wrong issuer.
            with pytest.raises(IdentityNotProvisioned):
                resolve_identity(conn, "https://other-idp.example/", subject)
    finally:
        _cleanup([pid], [ws])


def test_by_subject_composes_both_halves():
    ws = _workspace()
    pid = _person("Composed Director", legacy_clearance=4)
    _member(pid, ws, clearance=1, role="director")
    subject = f"sub-{uuid.uuid4()}"
    _identity(pid, subject)
    try:
        with store.pg(ws) as conn:
            p = resolve_principal_by_subject(conn, PROVIDER, subject, workspace_id=ws)
            # Clearance comes from the role mapping, not either stored column
            # (#166) — the composition must not have found a shortcut around
            # `resolve_principal_by_id`'s JOIN.
            assert p.clearance == 3
            assert p.role == "director"
            assert str(p.id) == pid
            assert p.workspace_id == ws
    finally:
        _cleanup([pid], [ws])


def test_by_subject_fails_closed_when_the_identity_has_no_membership_here():
    """Provisioned, authenticated, and still not admitted to this workspace.

    The two refusals are different on purpose: the first is about the account, the
    second about this tenant. Neither is an oracle — reaching either required proving
    control of the subject.
    """
    ws_a, ws_b = _workspace(), _workspace()
    pid = _person("Member Of B Only")
    _member(pid, ws_b, clearance=3, role="director")
    subject = f"sub-{uuid.uuid4()}"
    _identity(pid, subject)
    try:
        with store.pg(ws_a) as conn:
            with pytest.raises(PrincipalNotFound):
                resolve_principal_by_subject(conn, PROVIDER, subject, workspace_id=ws_a)
        with store.pg(ws_b) as conn:
            # 3 is 'director's mapped clearance (#166), not the stored value it
            # happens to equal here — see the other divergent-fixture tests for
            # why that distinction is asserted explicitly elsewhere.
            assert resolve_principal_by_subject(conn, PROVIDER, subject, workspace_id=ws_b).clearance == 3
    finally:
        _cleanup([pid], [ws_a, ws_b])


def test_by_subject_requires_an_explicit_workspace():
    import inspect

    sig = inspect.signature(resolve_principal_by_subject)
    assert sig.parameters["workspace_id"].default is inspect.Parameter.empty
