"""A non-approver's grant waits for a founder or admin (#225).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

---------------------------------------------------------------------------
WHAT THIS FILE HAS TO PROVE, AND WHY THE OBVIOUS TESTS ARE NOT ENOUGH
---------------------------------------------------------------------------
The maintainer's requirement (#225, recorded while signing the P4 gate) is one
sentence: a grant by any role other than `founder` or `admin` does not take effect
until a founder or admin approves it. The happy path for that is three assertions
long, and it is the least interesting thing here.

Four properties carry the actual weight, and each exists because the feature could
pass a naive test suite while failing it:

1. **Filing a request must not disturb an existing membership.** This is the reason
   the pending state lives in its own table rather than on the `membership` row
   (migration `0031`). Anti-escalation only checks the role being *requested*, so an
   investor may legitimately request `observer` for anyone — including an active
   founder. If pending were a state on the row, that request would suspend them.
   `test_filing_a_request_about_an_active_member_does_not_touch_their_membership`
   is the test that would have caught the rejected design, and it passes here for a
   structural reason rather than because a filter was remembered.

2. **Pending must not read.** Proven through `identity.resolve_principal_by_id` —
   the one query that decides who you are — not through an endpoint, because an
   endpoint's 403 could come from anywhere.

3. **A pending request must not outlive the authority that filed it.** Two tests,
   for revocation and for demotion. Both are refusals an implementation that trusts
   the request's own stored role would skip, and both leave `membership` untouched.

4. **The gate is what does the work.** `test_the_gate_is_what_defers_the_grant`
   widens `_APPROVER_ROLES` at runtime and shows the identical call then writing a
   membership directly. Without it, every assertion in this file is consistent with
   "the grant failed for some other reason", which is the vacuous-check shape
   `COORDINATION.md` §5 lists among the three that have already shipped here.

Signing in through `_signed_in()` gets a REAL cookie from `/auth/callback` plus
`/auth/workspace`, mirroring `test_workspace_membership_api.py` — the route-layer
assertions mean nothing against a forged session.

CLEANUP ORDER IS NOT ARBITRARY. `membership_request.requested_by` has no
`ON DELETE` clause (migration `0031`, deliberately: a principal must not be deleted
out from under the record of what they proposed), so request rows are removed before
their principals or the `DELETE FROM principal` fails on the foreign key. A cleanup
helper that got this wrong would leave every test in this file erroring in teardown.
"""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from callosum import identity
from meridian import workspaces

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip(
        "set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests",
        allow_module_level=True,
    )

from callosum.config import settings
from meridian.api import auth, errors
from meridian.api import workspaces as workspaces_api

pytestmark = pytest.mark.integration

ISSUER = "https://keycloak.example/realms/meridian"


def _admin(sql: str, params: tuple = ()) -> None:
    with psycopg.connect(settings().postgres_dsn) as conn:
        conn.execute(sql, params)
        conn.commit()


def _admin_fetch(sql: str, params: tuple = ()) -> list:
    from psycopg.rows import dict_row

    with psycopg.connect(settings().postgres_dsn, row_factory=dict_row) as conn:
        return conn.execute(sql, params).fetchall()


class _StubClient:
    def __init__(self, claims):
        self._claims = claims

    async def authorize_access_token(self, request):
        return {"userinfo": self._claims}


@pytest.fixture
def restore_client():
    original = auth._client
    yield
    auth._client = original


def _app(subject: str) -> FastAPI:
    application = FastAPI()
    application.add_middleware(SessionMiddleware, secret_key="test-secret-not-for-use")
    application.include_router(auth.router)
    application.include_router(workspaces_api.router)
    errors.install_exception_handlers(application)
    auth._client = lambda request: _StubClient({"sub": subject, "iss": ISSUER})  # type: ignore[assignment]
    return application


def _workspace(label: str) -> str:
    ws = str(uuid.uuid4())
    _admin(
        "INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s)",
        (ws, f"{label}-{ws[:6]}", ws),
    )
    return ws


def _principal(role: str = "founder", clearance: int | None = None) -> tuple[str, str]:
    pid = str(uuid.uuid4())
    subject = f"sub-{uuid.uuid4()}"
    resolved = clearance if clearance is not None else identity.ROLE_TO_CLEARANCE[role]
    _admin(
        "INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, %s, %s)",
        (pid, f"Approval Test {pid[:6]}", role, resolved),
    )
    _admin(
        "INSERT INTO principal_identity (principal_id, provider, subject) VALUES (%s, %s, %s)",
        (pid, ISSUER, subject),
    )
    return pid, subject


def _member(principal_id: str, workspace_id: str, role: str, clearance: int | None = None) -> None:
    resolved = clearance if clearance is not None else identity.ROLE_TO_CLEARANCE[role]
    _admin(
        "INSERT INTO membership (principal_id, workspace_id, role, clearance, active)"
        " VALUES (%s, %s, %s, %s, true)",
        (principal_id, workspace_id, role, resolved),
    )


def _cleanup(principal_ids: list[str], workspace_ids: list[str]) -> None:
    """Requests first — see the module docstring on `requested_by`'s missing ON DELETE."""
    for ws in workspace_ids:
        _admin("DELETE FROM membership_request WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM membership WHERE workspace_id = %s", (ws,))
    for pid in principal_ids:
        _admin("DELETE FROM principal WHERE id = %s", (pid,))
    for ws in workspace_ids:
        _admin("DELETE FROM workspace WHERE id = %s", (ws,))


def _signed_in(label: str, role: str) -> tuple[TestClient, str, str]:
    pid, subject = _principal(role=role)
    ws = _workspace(label)
    _member(pid, ws, role=role)

    client = TestClient(_app(subject), follow_redirects=False)
    assert client.get("/auth/callback").status_code == 303
    assert client.post("/auth/workspace", json={"workspace_id": ws}).status_code == 200
    return client, pid, ws


def _join(principal_id: str, workspace_id: str, role: str, subject: str) -> TestClient:
    """A second signed-in client in an EXISTING workspace."""
    _member(principal_id, workspace_id, role=role)
    client = TestClient(_app(subject), follow_redirects=False)
    assert client.get("/auth/callback").status_code == 303
    assert client.post("/auth/workspace", json={"workspace_id": workspace_id}).status_code == 200
    return client


def _memberships(principal_id: str, workspace_id: str) -> list:
    return _admin_fetch(
        "SELECT role, active FROM membership WHERE principal_id = %s AND workspace_id = %s",
        (principal_id, workspace_id),
    )


def _requests(workspace_id: str) -> list:
    return _admin_fetch(
        "SELECT * FROM membership_request WHERE workspace_id = %s ORDER BY created_at",
        (workspace_id,),
    )


def _events(workspace_id: str, aggregate_type: str) -> list:
    return _admin_fetch(
        "SELECT action, actor_principal_id, aggregate_id, payload FROM audit_event"
        " WHERE workspace_id = %s AND aggregate_type = %s ORDER BY created_at",
        (workspace_id, aggregate_type),
    )


# ---------------------------------------------------------------------------
# The deferral itself
# ---------------------------------------------------------------------------


class TestANonApproverGrantIsDeferred:
    def test_an_investor_grant_returns_202_and_writes_no_membership(self, restore_client):
        """The core of #225. 202, not 200, and `membership` is untouched."""
        client, founder, ws = _signed_in("defer_202", role="founder")
        investor, investor_sub = _principal(role="investor")
        client_i = _join(investor, ws, "investor", investor_sub)
        target, _ = _principal(role="observer")
        try:
            resp = client_i.post(
                "/api/membership", json={"principal_id": target, "role": "investor"}
            )
            assert resp.status_code == 202, resp.text

            body = resp.json()
            assert body["status"] == "pending"
            assert body["role"] == "investor"
            assert body["principal_id"] == target
            assert body["requested_by"] == investor
            # The 202 body is a request, not a membership: it must not carry the
            # fields a client would read to decide access has been granted.
            assert "active" not in body
            assert "clearance" not in body

            assert _memberships(target, ws) == []

            rows = _requests(ws)
            assert len(rows) == 1
            assert rows[0]["status"] == "pending"
            assert rows[0]["decided_by"] is None
            assert rows[0]["decided_at"] is None
        finally:
            _cleanup([founder, investor, target], [ws])

    def test_the_pending_principal_cannot_be_resolved_as_a_member(self, restore_client):
        """#225's "pending member cannot read", checked at the query that decides identity.

        Not through an endpoint: a 403 from a route could come from the session layer,
        the tenancy guard, or a clearance predicate. `resolve_principal_by_id` is the
        single join every one of those paths depends on, and a pending request must be
        invisible to it — which migration `0031` achieves by not being a membership at
        all, rather than by adding a filter this test would be pinning.
        """
        client, founder, ws = _signed_in("defer_noread", role="founder")
        exec_id, exec_sub = _principal(role="exec")
        client_e = _join(exec_id, ws, "exec", exec_sub)
        target, _ = _principal(role="observer")
        try:
            assert (
                client_e.post(
                    "/api/membership", json={"principal_id": target, "role": "director"}
                ).status_code
                == 202
            )

            from callosum import store

            with store.pg(ws) as conn:
                with pytest.raises(identity.PrincipalNotFound):
                    identity.resolve_principal_by_id(conn, target, workspace_id=ws)
        finally:
            _cleanup([founder, exec_id, target], [ws])

    def test_filing_a_request_about_an_active_member_does_not_touch_their_membership(
        self, restore_client
    ):
        """The test that rules out the rejected design (migration `0031`'s docstring).

        An investor (clearance 1) may legitimately request `observer` (0) for anybody,
        anti-escalation permits it, and the target here is an ACTIVE DIRECTOR. Had
        pending been a state on the `membership` row, filing this would have deactivated
        or demoted them — turning the approval requirement into a way for the least
        privileged role in the workspace to suspend one of the most privileged.

        The director's row must come out byte-identical, and they must still resolve at
        their own clearance.
        """
        client, founder, ws = _signed_in("defer_nodos", role="founder")
        investor, investor_sub = _principal(role="investor")
        client_i = _join(investor, ws, "investor", investor_sub)
        director, _ = _principal(role="director")
        _member(director, ws, "director")
        try:
            before = _memberships(director, ws)[0]

            resp = client_i.post(
                "/api/membership", json={"principal_id": director, "role": "observer"}
            )
            assert resp.status_code == 202, resp.text

            assert _memberships(director, ws)[0] == before

            from callosum import store

            with store.pg(ws) as conn:
                resolved = identity.resolve_principal_by_id(conn, director, workspace_id=ws)
            assert resolved.role == "director"
            assert resolved.clearance == identity.ROLE_TO_CLEARANCE["director"]
        finally:
            _cleanup([founder, investor, director], [ws])

    def test_anti_escalation_still_refuses_before_a_request_is_filed(self, restore_client):
        """A request that could never be approved is not filed at all.

        The ceiling runs before the approver branch, so an investor asking for `founder`
        gets the same 403 as before #225 — not a pending request for an approver to
        discover and refuse later.
        """
        client, founder, ws = _signed_in("defer_ceiling", role="founder")
        investor, investor_sub = _principal(role="investor")
        client_i = _join(investor, ws, "investor", investor_sub)
        target, _ = _principal(role="observer")
        try:
            resp = client_i.post(
                "/api/membership", json={"principal_id": target, "role": "founder"}
            )
            assert resp.status_code == 403, resp.text
            assert _requests(ws) == []
            assert _memberships(target, ws) == []
        finally:
            _cleanup([founder, investor, target], [ws])

    def test_filing_is_audited_even_if_nobody_ever_answers_it(self, restore_client):
        client, founder, ws = _signed_in("defer_audit", role="founder")
        advisor, advisor_sub = _principal(role="advisor")
        client_a = _join(advisor, ws, "advisor", advisor_sub)
        target, _ = _principal(role="observer")
        try:
            resp = client_a.post(
                "/api/membership", json={"principal_id": target, "role": "advisor"}
            )
            assert resp.status_code == 202

            events = _events(ws, "membership_request")
            assert [e["action"] for e in events] == ["created"]
            assert str(events[0]["actor_principal_id"]) == advisor
            assert events[0]["payload"]["principal_id"] == target
            assert events[0]["payload"]["status"] == "pending"

            # And nothing was recorded against the membership aggregate: no grant
            # happened, so the trail must not suggest one did.
            assert _events(ws, "membership") == []
        finally:
            _cleanup([founder, advisor, target], [ws])

    def test_the_gate_is_what_defers_the_grant(self, restore_client, monkeypatch):
        """Red-proof: widen `_APPROVER_ROLES` and the identical call grants directly.

        Every other assertion in this file is also consistent with "the exec's grant
        failed for an unrelated reason". This one removes that reading: with `exec` added
        to the approver set and nothing else changed, the same request returns 200, writes
        a live membership, and files no request. The role check is therefore what produces
        the deferral.
        """
        client, founder, ws = _signed_in("defer_mutation", role="founder")
        exec_id, exec_sub = _principal(role="exec")
        client_e = _join(exec_id, ws, "exec", exec_sub)
        target, _ = _principal(role="observer")
        try:
            monkeypatch.setattr(
                workspaces, "_APPROVER_ROLES", frozenset({"founder", "admin", "exec"})
            )
            resp = client_e.post(
                "/api/membership", json={"principal_id": target, "role": "director"}
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["active"] is True
            assert _memberships(target, ws)[0] == {"role": "director", "active": True}
            assert _requests(ws) == []
        finally:
            _cleanup([founder, exec_id, target], [ws])


class TestAnApproverGrantsDirectly:
    @pytest.mark.parametrize("role", ["founder", "admin"])
    def test_an_approvers_grant_still_takes_effect_immediately(self, restore_client, role):
        """The pre-#225 contract, unchanged — including the 200 and the body shape.

        Parametrized over both approver roles rather than testing `founder` alone: `admin`
        is the half of the pair that carries membership-management authority *without*
        being the workspace's creator, and it is the one a clearance-derived
        implementation would be most likely to get right by accident and a role-derived
        one to leave out.
        """
        client, actor, ws = _signed_in(f"direct_{role}", role=role)
        target, _ = _principal(role="observer")
        try:
            resp = client.post("/api/membership", json={"principal_id": target, "role": "advisor"})
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["role"] == "advisor"
            assert body["active"] is True
            assert body["clearance"] == identity.ROLE_TO_CLEARANCE["advisor"]

            assert _memberships(target, ws)[0] == {"role": "advisor", "active": True}
            assert _requests(ws) == []
            assert [e["action"] for e in _events(ws, "membership")] == ["created"]
        finally:
            _cleanup([actor, target], [ws])


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------


def _pending(label: str, requester_role: str = "exec", granted_role: str = "director"):
    """A workspace with a founder, a non-approver, and one pending request.

    Returns everything the approval tests need to act and to clean up.
    """
    client_f, founder, ws = _signed_in(label, role="founder")
    requester, requester_sub = _principal(role=requester_role)
    client_r = _join(requester, ws, requester_role, requester_sub)
    target, _ = _principal(role="observer")

    resp = client_r.post("/api/membership", json={"principal_id": target, "role": granted_role})
    assert resp.status_code == 202, resp.text
    request_id = resp.json()["id"]
    return client_f, founder, requester, requester_sub, target, ws, request_id


class TestApproval:
    def test_a_founder_approval_makes_the_membership_live_and_readable(self, restore_client):
        client_f, founder, requester, _, target, ws, request_id = _pending("appr_happy")
        try:
            resp = client_f.post(f"/api/membership/requests/{request_id}/approve")
            assert resp.status_code == 200, resp.text
            assert resp.json()["role"] == "director"
            assert resp.json()["active"] is True

            assert _memberships(target, ws)[0] == {"role": "director", "active": True}

            row = _requests(ws)[0]
            assert row["status"] == "approved"
            assert str(row["decided_by"]) == founder
            assert row["decided_at"] is not None

            from callosum import store

            with store.pg(ws) as conn:
                resolved = identity.resolve_principal_by_id(conn, target, workspace_id=ws)
            assert resolved.clearance == identity.ROLE_TO_CLEARANCE["director"]
        finally:
            _cleanup([founder, requester, target], [ws])

    def test_approval_writes_two_events_naming_both_people(self, restore_client):
        """The attribution #225 exists to create.

        A grant that reached a membership through an approval has two authors, and a
        trail that names only one of them is the gap the requirement was added to close.
        The `membership` event's ACTOR is the approver — whose signature made it
        effective — and its payload names the requester; the `membership_request` event
        records what happened to the queue entry.
        """
        client_f, founder, requester, _, target, ws, request_id = _pending("appr_audit")
        try:
            assert client_f.post(f"/api/membership/requests/{request_id}/approve").status_code == 200

            membership_events = _events(ws, "membership")
            assert [e["action"] for e in membership_events] == ["created"]
            grant = membership_events[0]
            assert str(grant["actor_principal_id"]) == founder
            assert str(grant["aggregate_id"]) == target
            assert grant["payload"]["requested_by"] == requester
            assert grant["payload"]["request_id"] == request_id

            request_events = _events(ws, "membership_request")
            assert [e["action"] for e in request_events] == ["created", "approved"]
            assert str(request_events[1]["actor_principal_id"]) == founder
            assert request_events[1]["payload"]["requested_by"] == requester
        finally:
            _cleanup([founder, requester, target], [ws])

    def test_a_non_approver_cannot_approve(self, restore_client):
        """#225's named requirement. The second non-admin is a *different* member from
        the requester, so the refusal is about the role and not about self-approval."""
        client_f, founder, requester, _, target, ws, request_id = _pending("appr_notadmin")
        other, other_sub = _principal(role="director")
        client_o = _join(other, ws, "director", other_sub)
        try:
            resp = client_o.post(f"/api/membership/requests/{request_id}/approve")
            assert resp.status_code == 403, resp.text
            assert _memberships(target, ws) == []
            assert _requests(ws)[0]["status"] == "pending"
        finally:
            _cleanup([founder, requester, other, target], [ws])

    def test_the_requester_cannot_approve_their_own_request_even_once_promoted(
        self, restore_client
    ):
        """#225's "a self-approval is refused", by the only route that reaches it.

        A requester is never an approver at filing time — that is what made the request
        pending. So the check is only reachable through promotion: the founder makes the
        exec an admin, and the exec's own pending request must still not be self-signed.
        Without this, the requirement is two API calls away from being undone.
        """
        client_f, founder, requester, requester_sub, target, ws, request_id = _pending(
            "appr_self"
        )
        try:
            # The founder promotes the requester to admin — a direct grant, 200.
            assert (
                client_f.post(
                    "/api/membership", json={"principal_id": requester, "role": "admin"}
                ).status_code
                == 200
            )

            client_r = TestClient(_app(requester_sub), follow_redirects=False)
            assert client_r.get("/auth/callback").status_code == 303
            assert client_r.post("/auth/workspace", json={"workspace_id": ws}).status_code == 200

            resp = client_r.post(f"/api/membership/requests/{request_id}/approve")
            assert resp.status_code == 403, resp.text
            assert _memberships(target, ws) == []
            assert _requests(ws)[0]["status"] == "pending"

            # And the gate really was self-approval, not authority: the founder can
            # still sign the very same request.
            assert client_f.post(f"/api/membership/requests/{request_id}/approve").status_code == 200
            assert _memberships(target, ws)[0]["role"] == "director"
        finally:
            _cleanup([founder, requester, target], [ws])

    def test_approving_twice_is_a_conflict_not_a_second_grant(self, restore_client):
        client_f, founder, requester, _, target, ws, request_id = _pending("appr_twice")
        try:
            assert client_f.post(f"/api/membership/requests/{request_id}/approve").status_code == 200
            resp = client_f.post(f"/api/membership/requests/{request_id}/approve")
            assert resp.status_code == 409, resp.text

            # One grant event, not two: the second call must not re-write the membership.
            assert [e["action"] for e in _events(ws, "membership")] == ["created"]
        finally:
            _cleanup([founder, requester, target], [ws])

    def test_an_unknown_request_id_is_a_404(self, restore_client):
        client_f, founder, requester, _, target, ws, request_id = _pending("appr_404")
        try:
            resp = client_f.post(f"/api/membership/requests/{uuid.uuid4()}/approve")
            assert resp.status_code == 404, resp.text
        finally:
            _cleanup([founder, requester, target], [ws])

    def test_an_approver_cannot_reach_a_request_filed_in_another_workspace(self, restore_client):
        """Tenancy, at the one route that takes an opaque id from the caller.

        Unlike `grant` and `revoke` — whose cross-workspace attacks are unrepresentable
        because the only identifiers they accept are a principal and the session's own
        workspace — approve and reject take a `request_id` the caller supplies. That is a
        handle to a row in a table that holds every workspace's requests, so this is a
        refusal that has to be *made*, not one the route shape provides for free.
        """
        client_a, founder_a, ws_a = _signed_in("appr_cross_a", role="founder")
        client_b, founder_b, requester_b, _, target_b, ws_b, request_id = _pending("appr_cross_b")
        try:
            resp = client_a.post(f"/api/membership/requests/{request_id}/approve")
            assert resp.status_code == 404, resp.text

            assert _requests(ws_b)[0]["status"] == "pending"
            assert _memberships(target_b, ws_b) == []
            assert _events(ws_b, "membership") == []
        finally:
            _cleanup([founder_a], [ws_a])
            _cleanup([founder_b, requester_b, target_b], [ws_b])

    def test_the_approver_check_reads_role_not_the_stored_clearance_column(self, restore_client):
        """Approver-ship is a role, and `membership.clearance` cannot confer it.

        The exact drift `revoke_membership`'s docstring documents and #182 counts fifteen
        fixtures of: `membership.role` and `membership.clearance` are two columns with
        nothing forcing them to agree, and `cli.py:125` seeds the latter independently of
        the former. This member's stored clearance says 4 — the approver level — while
        their role says `advisor`. They must not be able to approve.

        It is also the test behind `_APPROVER_ROLES`'s comment: membership-management
        authority is a separate grant from clearance (`identity.ROLE_TO_CLEARANCE`'s own
        note), so no clearance value may stand in for the role.
        """
        client_f, founder, requester, _, target, ws, request_id = _pending("appr_drift")
        impostor, impostor_sub = _principal(role="advisor")
        _admin(
            "INSERT INTO membership (principal_id, workspace_id, role, clearance, active)"
            " VALUES (%s, %s, 'advisor', 4, true)",
            (impostor, ws),
        )
        client_x = TestClient(_app(impostor_sub), follow_redirects=False)
        try:
            assert client_x.get("/auth/callback").status_code == 303
            assert client_x.post("/auth/workspace", json={"workspace_id": ws}).status_code == 200

            resp = client_x.post(f"/api/membership/requests/{request_id}/approve")
            assert resp.status_code == 403, resp.text
            assert _memberships(target, ws) == []
        finally:
            _cleanup([founder, requester, impostor, target], [ws])


class TestTheRequestersAuthorityIsRevalidated:
    def test_revoking_the_requester_makes_their_pending_request_unapprovable(
        self, restore_client
    ):
        """Revocation has to retract what the revoked member set in motion.

        Otherwise removing somebody for cause leaves their requests live, to be signed
        later by an approver with no reason to know the requester is gone. 409, because
        the approver's move is to re-read the queue — the request is not malformed and
        the approver is not unauthorized.
        """
        client_f, founder, requester, _, target, ws, request_id = _pending("appr_revoked")
        try:
            assert client_f.post(f"/api/membership/{requester}/revoke").status_code == 200

            resp = client_f.post(f"/api/membership/requests/{request_id}/approve")
            assert resp.status_code == 409, resp.text
            assert resp.json()["error"]["code"] == "stale_resource"

            assert _memberships(target, ws) == []
            assert _requests(ws)[0]["status"] == "pending"
            assert _events(ws, "membership_request")[-1]["action"] == "created"
        finally:
            _cleanup([founder, requester, target], [ws])

    def test_demoting_the_requester_below_the_requested_role_blocks_approval(
        self, restore_client
    ):
        """The same hole one rung down.

        The exec asked to grant `director` (clearance 3), which they could do. Demoted to
        `observer` (0) they could not file that request today — so the one they filed
        yesterday must not still be honoured. The refusal is about the REQUESTER's
        current standing; the founder approving has clearance 4 and is not the problem.
        """
        client_f, founder, requester, _, target, ws, request_id = _pending("appr_demoted")
        try:
            assert (
                client_f.post(
                    "/api/membership", json={"principal_id": requester, "role": "observer"}
                ).status_code
                == 200
            )

            resp = client_f.post(f"/api/membership/requests/{request_id}/approve")
            assert resp.status_code == 409, resp.text
            assert resp.json()["error"]["code"] == "stale_resource"
            assert _memberships(target, ws) == []
        finally:
            _cleanup([founder, requester, target], [ws])

    def test_a_stale_request_can_still_be_rejected(self, restore_client):
        """The asymmetry `reject_membership_request`'s docstring argues for.

        If the thing that makes a request unapprovable also made it unrejectable, the
        pending row would be permanent — and because `uq_membership_request_pending`
        allows one open request per principal, the grant path for `target` would be
        wedged forever. Rejection has to be the available side.
        """
        client_f, founder, requester, _, target, ws, request_id = _pending("appr_stale_reject")
        try:
            assert client_f.post(f"/api/membership/{requester}/revoke").status_code == 200
            assert client_f.post(f"/api/membership/requests/{request_id}/approve").status_code == 409

            resp = client_f.post(f"/api/membership/requests/{request_id}/reject")
            assert resp.status_code == 200, resp.text
            assert resp.json()["status"] == "rejected"
            assert _requests(ws)[0]["status"] == "rejected"
        finally:
            _cleanup([founder, requester, target], [ws])


# ---------------------------------------------------------------------------
# Rejection and the queue
# ---------------------------------------------------------------------------


class TestRejection:
    def test_rejection_writes_no_membership_and_is_audited(self, restore_client):
        client_f, founder, requester, _, target, ws, request_id = _pending("rej_happy")
        try:
            resp = client_f.post(f"/api/membership/requests/{request_id}/reject")
            assert resp.status_code == 200, resp.text
            assert resp.json()["status"] == "rejected"

            assert _memberships(target, ws) == []
            row = _requests(ws)[0]
            assert row["status"] == "rejected"
            assert str(row["decided_by"]) == founder

            assert [e["action"] for e in _events(ws, "membership_request")] == [
                "created",
                "rejected",
            ]
            # A refusal is not a grant: nothing may appear against the membership
            # aggregate, or an audit reader would see access that was never given.
            assert _events(ws, "membership") == []
        finally:
            _cleanup([founder, requester, target], [ws])

    def test_a_non_approver_cannot_reject(self, restore_client):
        client_f, founder, requester, _, target, ws, request_id = _pending("rej_notadmin")
        other, other_sub = _principal(role="director")
        client_o = _join(other, ws, "director", other_sub)
        try:
            assert client_o.post(f"/api/membership/requests/{request_id}/reject").status_code == 403
            assert _requests(ws)[0]["status"] == "pending"
        finally:
            _cleanup([founder, requester, other, target], [ws])

    def test_rejecting_twice_is_a_conflict(self, restore_client):
        client_f, founder, requester, _, target, ws, request_id = _pending("rej_twice")
        try:
            assert client_f.post(f"/api/membership/requests/{request_id}/reject").status_code == 200
            assert client_f.post(f"/api/membership/requests/{request_id}/reject").status_code == 409
            assert [e["action"] for e in _events(ws, "membership_request")] == [
                "created",
                "rejected",
            ]
        finally:
            _cleanup([founder, requester, target], [ws])

    def test_an_approved_request_cannot_then_be_rejected(self, restore_client):
        """The membership is already live; a later rejection must not pretend otherwise.

        Revoking it is `POST /api/membership/{id}/revoke` — a different act, with its own
        anti-escalation and its own last-member guard. Letting `reject` flip a decided row
        would leave the queue claiming the grant was refused while the membership it
        created was still active.
        """
        client_f, founder, requester, _, target, ws, request_id = _pending("rej_after_appr")
        try:
            assert client_f.post(f"/api/membership/requests/{request_id}/approve").status_code == 200
            assert client_f.post(f"/api/membership/requests/{request_id}/reject").status_code == 409
            assert _requests(ws)[0]["status"] == "approved"
            assert _memberships(target, ws)[0]["active"] is True
        finally:
            _cleanup([founder, requester, target], [ws])


class TestTheQueueIsBounded:
    def test_a_second_pending_request_for_the_same_principal_is_a_409(self, restore_client):
        """`uq_membership_request_pending`, surfaced as a domain refusal rather than a 500.

        Without the index a non-approver could file the same request without limit and
        make the approver's queue unusable; without this mapping the refusal would reach
        the client as an internal error.
        """
        client_f, founder, requester, requester_sub, target, ws, request_id = _pending(
            "queue_dup"
        )
        client_r = TestClient(_app(requester_sub), follow_redirects=False)
        try:
            assert client_r.get("/auth/callback").status_code == 303
            assert client_r.post("/auth/workspace", json={"workspace_id": ws}).status_code == 200

            resp = client_r.post(
                "/api/membership", json={"principal_id": target, "role": "advisor"}
            )
            assert resp.status_code == 409, resp.text
            assert len(_requests(ws)) == 1

            # The refusal left no audit event — nothing happened, so nothing is recorded
            # as having happened, matching `revoke_membership`'s last-member refusal.
            assert [e["action"] for e in _events(ws, "membership_request")] == ["created"]
        finally:
            _cleanup([founder, requester, target], [ws])

    def test_rejecting_frees_the_slot_for_a_new_request(self, restore_client):
        """The partial index exempts decided rows, which is what makes `reject` an exit.

        This is the pair to the test above: the uniqueness that bounds the queue must not
        bound it permanently, or one unanswered request would lock the grant path for that
        principal for the lifetime of the workspace.
        """
        client_f, founder, requester, requester_sub, target, ws, request_id = _pending(
            "queue_reopen"
        )
        client_r = TestClient(_app(requester_sub), follow_redirects=False)
        try:
            assert client_r.get("/auth/callback").status_code == 303
            assert client_r.post("/auth/workspace", json={"workspace_id": ws}).status_code == 200

            assert client_f.post(f"/api/membership/requests/{request_id}/reject").status_code == 200

            resp = client_r.post(
                "/api/membership", json={"principal_id": target, "role": "advisor"}
            )
            assert resp.status_code == 202, resp.text

            rows = _requests(ws)
            assert len(rows) == 2
            assert sorted(r["status"] for r in rows) == ["pending", "rejected"]
        finally:
            _cleanup([founder, requester, target], [ws])

    def test_two_pending_requests_for_different_principals_coexist(self, restore_client):
        """The index is scoped per principal, not per workspace — one open request about
        Alice must not block one about Bob."""
        client_f, founder, requester, requester_sub, target, ws, _ = _pending("queue_two")
        second, _ = _principal(role="observer")
        client_r = TestClient(_app(requester_sub), follow_redirects=False)
        try:
            assert client_r.get("/auth/callback").status_code == 303
            assert client_r.post("/auth/workspace", json={"workspace_id": ws}).status_code == 200

            resp = client_r.post(
                "/api/membership", json={"principal_id": second, "role": "advisor"}
            )
            assert resp.status_code == 202, resp.text
            assert len(_requests(ws)) == 2
        finally:
            _cleanup([founder, requester, target, second], [ws])


class TestTheQueueRead:
    def test_an_approver_sees_the_pending_queue_oldest_first(self, restore_client):
        client_f, founder, requester, requester_sub, target, ws, request_id = _pending(
            "read_queue"
        )
        second, _ = _principal(role="observer")
        client_r = TestClient(_app(requester_sub), follow_redirects=False)
        try:
            assert client_r.get("/auth/callback").status_code == 303
            assert client_r.post("/auth/workspace", json={"workspace_id": ws}).status_code == 200
            assert (
                client_r.post(
                    "/api/membership", json={"principal_id": second, "role": "advisor"}
                ).status_code
                == 202
            )

            resp = client_f.get("/api/membership/requests")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert [r["principal_id"] for r in body] == [target, second]
            assert {r["status"] for r in body} == {"pending"}
            assert {r["requested_by"] for r in body} == {requester}
        finally:
            _cleanup([founder, requester, target, second], [ws])

    def test_a_non_approver_is_refused_the_queue_outright(self, restore_client):
        """All-or-nothing, not a filtered subset — see `list_pending_requests`'s docstring
        on why ADR-018's count-or-erase rule does not apply here."""
        client_f, founder, requester, requester_sub, target, ws, _ = _pending("read_403")
        client_r = TestClient(_app(requester_sub), follow_redirects=False)
        try:
            assert client_r.get("/auth/callback").status_code == 303
            assert client_r.post("/auth/workspace", json={"workspace_id": ws}).status_code == 200

            resp = client_r.get("/api/membership/requests")
            assert resp.status_code == 403, resp.text
            assert resp.json()["error"]["code"] == "forbidden"
        finally:
            _cleanup([founder, requester, target], [ws])

    def test_the_queue_shows_only_this_workspace_and_only_pending(self, restore_client):
        """Two properties in one scene, because they share a fixture and each is cheap.

        Tenancy: the founder of `ws_a` must not see `ws_b`'s request even though both
        rows live in one table. Scope: a decided request leaves the queue — a queue that
        lists what it has already answered stops being one.
        """
        client_a, founder_a, ws_a = _signed_in("read_cross_a", role="founder")
        client_b, founder_b, requester_b, _, target_b, ws_b, request_id = _pending("read_cross_b")
        try:
            assert client_a.get("/api/membership/requests").json() == []

            assert len(client_b.get("/api/membership/requests").json()) == 1
            assert client_b.post(f"/api/membership/requests/{request_id}/reject").status_code == 200
            assert client_b.get("/api/membership/requests").json() == []
        finally:
            _cleanup([founder_a], [ws_a])
            _cleanup([founder_b, requester_b, target_b], [ws_b])
