"""The membership route boundary is untested, until now (#166 step 7).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

---------------------------------------------------------------------------
THE GAP THESE TESTS EXIST FOR
---------------------------------------------------------------------------
Every existing test for `grant_membership`/`revoke_membership`
(`tests/test_workspace_bootstrap.py`) calls the domain functions directly,
passing `workspace_id` as a plain argument. That proves the domain logic is
correct; it proves nothing about the route wiring in front of it — the part
that resolves the session, extracts `CurrentPrincipal`, and (per ADR-013 and
the maintainer's #166 step 5 ruling) must take the target workspace from the
caller's own session, never from the request body.

Signing in through `_signed_in()` (mirroring
`test_prep_api_authorization.py:152`) gets a REAL cookie set by `/auth/callback`
and `/auth/workspace`, not a forged session — the same discipline that file's
own docstring insists on.

One property shapes these tests rather than being assumed: at the route layer
a cross-workspace grant or revoke CANNOT BE EXPRESSED AT ALL.
`MembershipGrant` has no `workspace_id` field (`extra="forbid"` rejects one if
supplied), and `revoke`'s only path parameter is `principal_id`. So there is
nothing to refuse — the tests below demonstrate the absence of the attack
surface rather than a refusal of it.
"""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip(
        "set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests",
        allow_module_level=True,
    )

from callosum import identity
from callosum.config import settings
from meridian.api import auth, errors
from meridian.api import workspaces as workspaces_api

pytestmark = pytest.mark.integration

ISSUER = "https://keycloak.example/realms/meridian"
DIRECTOR_CLEARANCE = identity.ROLE_TO_CLEARANCE["director"]


def _admin(sql: str, params: tuple = ()) -> None:
    with psycopg.connect(settings().postgres_dsn) as conn:
        conn.execute(sql, params)
        conn.commit()


def _admin_fetch(sql: str, params: tuple = ()):
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


def _principal_with_identity(role: str = "founder", clearance: int | None = None) -> tuple[str, str]:
    pid = str(uuid.uuid4())
    subject = f"sub-{uuid.uuid4()}"
    resolved = clearance if clearance is not None else identity.ROLE_TO_CLEARANCE[role]
    _admin(
        "INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, %s, %s)",
        (pid, f"API Test {pid[:6]}", role, resolved),
    )
    _admin(
        "INSERT INTO principal_identity (principal_id, provider, subject) VALUES (%s, %s, %s)",
        (pid, ISSUER, subject),
    )
    return pid, subject


def _member(principal_id: str, workspace_id: str, role: str = "founder", clearance: int | None = None) -> None:
    resolved = clearance if clearance is not None else identity.ROLE_TO_CLEARANCE[role]
    _admin(
        "INSERT INTO membership (principal_id, workspace_id, role, clearance, active)"
        " VALUES (%s, %s, %s, %s, true)",
        (principal_id, workspace_id, role, resolved),
    )


def _cleanup(principal_ids: list[str], workspace_ids: list[str]) -> None:
    for ws in workspace_ids:
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM membership WHERE workspace_id = %s", (ws,))
    for pid in principal_ids:
        _admin("DELETE FROM principal WHERE id = %s", (pid,))
    for ws in workspace_ids:
        _admin("DELETE FROM workspace WHERE id = %s", (ws,))


def _signed_in(label: str, role: str = "founder") -> tuple[TestClient, str, str]:
    """A client that has signed in AND legitimately selected its workspace.

    Mirrors `test_prep_api_authorization.py:152` exactly: the cookie comes from
    a real `/auth/callback` + `/auth/workspace` round trip, not a forged
    session, which is what makes the membership-write assertions below mean
    anything.
    """
    pid, subject = _principal_with_identity(role=role)
    ws = _workspace(label)
    _member(pid, ws, role=role)

    client = TestClient(_app(subject), follow_redirects=False)
    assert client.get("/auth/callback").status_code == 303
    assert client.post("/auth/workspace", json={"workspace_id": ws}).status_code == 200
    return client, pid, ws


class TestGrantRouteWiring:
    def test_a_signed_in_founder_can_grant_through_the_route(self, restore_client):
        """The happy path through the ACTUAL route, not the domain function —
        the gap this whole file exists to close.
        """
        client, founder, ws = _signed_in("api_grant_happy", role="founder")
        target = str(uuid.uuid4())
        _admin("INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, %s, %s)",
               (target, "Grant Target", "observer", identity.ROLE_TO_CLEARANCE["observer"]))
        try:
            resp = client.post("/api/membership", json={"principal_id": target, "role": "advisor"})
            assert resp.status_code == 200
            body = resp.json()
            assert body["role"] == "advisor"
            assert body["active"] is True

            row = _admin_fetch(
                "SELECT role, active FROM membership WHERE principal_id = %s AND workspace_id = %s",
                (target, ws),
            )[0]
            assert row["role"] == "advisor"
            assert row["active"] is True

            events = _admin_fetch(
                "SELECT action, actor_principal_id FROM audit_event"
                " WHERE workspace_id = %s AND aggregate_type = 'membership' AND aggregate_id = %s",
                (ws, target),
            )
            assert [e["action"] for e in events] == ["created"]
            assert str(events[0]["actor_principal_id"]) == founder
        finally:
            _cleanup([founder, target], [ws])

    def test_four_role_rejections_exact_match_not_fuzzy(self, restore_client):
        """Role validation at the route is exact-match, not case- or
        whitespace-tolerant. Four distinct rejections, not one, because each
        exercises a different way a client-supplied string can fail to be a
        real role: not a role at all, empty, right word wrong case, right word
        with stray whitespace. All four must be refused before any write.
        """
        client, founder, ws = _signed_in("api_grant_roles", role="founder")
        target = str(uuid.uuid4())
        _admin("INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, %s, %s)",
               (target, "Role Reject Target", "observer", identity.ROLE_TO_CLEARANCE["observer"]))
        try:
            for bad_role in ("superuser", "", "Founder", " founder"):
                resp = client.post("/api/membership", json={"principal_id": target, "role": bad_role})
                assert resp.status_code == 422, f"role={bad_role!r} should be refused, got {resp.status_code}"

            rows = _admin_fetch(
                "SELECT 1 FROM membership WHERE principal_id = %s AND workspace_id = %s",
                (target, ws),
            )
            assert rows == [], "none of the four rejections may have written a membership row"
        finally:
            _cleanup([founder, target], [ws])

    def test_a_workspace_id_field_in_the_body_does_not_exist_to_supply(self, restore_client):
        """Demonstrates the inexpressibility directly rather than assuming it:
        `MembershipGrant`'s `extra="forbid"` means attempting to name a
        workspace in the request body is itself a validation error, not a
        silently-ignored field and not a routing decision made at request time.
        """
        client, founder, ws = _signed_in("api_grant_no_ws_field", role="founder")
        target = str(uuid.uuid4())
        _admin("INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, %s, %s)",
               (target, "No Field Target", "observer", identity.ROLE_TO_CLEARANCE["observer"]))
        try:
            resp = client.post(
                "/api/membership",
                json={"principal_id": target, "role": "advisor", "workspace_id": str(uuid.uuid4())},
            )
            assert resp.status_code == 422

            rows = _admin_fetch(
                "SELECT 1 FROM membership WHERE principal_id = %s AND workspace_id = %s",
                (target, ws),
            )
            assert rows == []
        finally:
            _cleanup([founder, target], [ws])

    def test_a_grant_naming_a_member_of_another_workspace_affects_only_the_callers_own(self, restore_client):
        """The property the module docstring names: a cross-workspace grant is
        not refused, it is UNREPRESENTABLE. `target` already holds a real,
        active membership in `ws_b`; signing into `ws_a` and granting `target`
        a role there can only ever create/modify a row scoped to `ws_a` —
        there is no field through which `ws_b` could even be named. `ws_b`'s
        row, and its audit history, must come out byte-identical.
        """
        client_a, founder_a, ws_a = _signed_in("api_grant_cross_a", role="founder")
        founder_b, _ = _principal_with_identity(role="founder")
        ws_b = _workspace("api_grant_cross_b")
        _member(founder_b, ws_b, role="founder")

        target, _ = _principal_with_identity(role="observer")
        _member(target, ws_b, role="observer")
        try:
            b_row_before = _admin_fetch(
                "SELECT role, active, clearance FROM membership"
                " WHERE principal_id = %s AND workspace_id = %s",
                (target, ws_b),
            )[0]

            resp = client_a.post("/api/membership", json={"principal_id": target, "role": "advisor"})
            assert resp.status_code == 200

            a_row = _admin_fetch(
                "SELECT role, active FROM membership WHERE principal_id = %s AND workspace_id = %s",
                (target, ws_a),
            )[0]
            assert a_row == {"role": "advisor", "active": True}

            b_row_after = _admin_fetch(
                "SELECT role, active, clearance FROM membership"
                " WHERE principal_id = %s AND workspace_id = %s",
                (target, ws_b),
            )[0]
            assert b_row_after == b_row_before

            b_events = _admin_fetch(
                "SELECT 1 FROM audit_event WHERE workspace_id = %s AND aggregate_id = %s",
                (ws_b, target),
            )
            assert b_events == []
        finally:
            _cleanup([founder_a, founder_b, target], [ws_a, ws_b])


class TestRevokeRouteWiring:
    def test_a_signed_in_founder_can_revoke_through_the_route(self, restore_client):
        client, founder, ws = _signed_in("api_revoke_happy", role="founder")
        target, _ = _principal_with_identity(role="advisor")
        _member(target, ws, role="advisor")
        try:
            resp = client.post(f"/api/membership/{target}/revoke")
            assert resp.status_code == 200
            assert resp.json()["active"] is False

            row = _admin_fetch(
                "SELECT active FROM membership WHERE principal_id = %s AND workspace_id = %s",
                (target, ws),
            )[0]
            assert row["active"] is False
        finally:
            _cleanup([founder, target], [ws])

    def test_the_last_active_member_refusal_survives_the_route_as_409(self, restore_client):
        """6C: the #185 guard must not regress, checked here at the layer that
        was never checked before — the route, not the domain function.
        """
        client, founder, ws = _signed_in("api_revoke_last_member", role="founder")
        try:
            resp = client.post(f"/api/membership/{founder}/revoke")
            assert resp.status_code == 409

            row = _admin_fetch(
                "SELECT active FROM membership WHERE principal_id = %s AND workspace_id = %s",
                (founder, ws),
            )[0]
            assert row["active"] is True
        finally:
            _cleanup([founder], [ws])

    def test_revoking_a_principal_who_is_only_a_member_of_another_workspace_fails(self, restore_client):
        """Symmetric to the grant inexpressibility test: `target` is a real
        member of `ws_b` only. Signed into `ws_a`, `revoke`'s sole parameter is
        `principal_id` — there is still no field for `ws_b` — so this cannot
        reach `target`'s real membership at all; it looks for one in `ws_a`,
        finds none, and 404s.
        """
        client_a, founder_a, ws_a = _signed_in("api_revoke_cross_a", role="founder")
        founder_b, _ = _principal_with_identity(role="founder")
        ws_b = _workspace("api_revoke_cross_b")
        _member(founder_b, ws_b, role="founder")
        target, _ = _principal_with_identity(role="advisor")
        _member(target, ws_b, role="advisor")
        try:
            resp = client_a.post(f"/api/membership/{target}/revoke")
            assert resp.status_code == 404

            row = _admin_fetch(
                "SELECT active FROM membership WHERE principal_id = %s AND workspace_id = %s",
                (target, ws_b),
            )[0]
            assert row["active"] is True
        finally:
            _cleanup([founder_a, founder_b, target], [ws_a, ws_b])
