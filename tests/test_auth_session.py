"""OIDC session and auth routes (Meridian P3, CP-A/A3 — ADR-009/010/011).

These do **not** talk to Keycloak. The OIDC client is replaced with a stub that
returns claims, because what needs testing is what this codebase does with a validated
token — resolve the subject, refuse an unprovisioned one, and put the right things in
the session. Whether authlib validates a signature correctly is authlib's test suite's
job, and standing up an IdP to re-answer it would make the gated suite slow and
non-deterministic for no coverage gained.

The session-contents tests are the important ones. A cookie that carries a clearance
is a cached authorization, and it keeps being true after the fact stops being.
"""

import os
import uuid

import pytest

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip("set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests", allow_module_level=True)

import psycopg
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from callosum.config import settings
from meridian.api import auth
from meridian.api import session as sess

pytestmark = pytest.mark.integration

ISSUER = "https://keycloak.example/realms/meridian"


def _admin(sql: str, params: tuple = ()) -> None:
    with psycopg.connect(settings().postgres_dsn) as conn:
        conn.execute(sql, params)
        conn.commit()


def _provisioned_principal(subject: str) -> str:
    pid = str(uuid.uuid4())
    _admin(
        "INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, 'director', 2)",
        (pid, f"OIDC User {pid[:6]}"),
    )
    _admin(
        "INSERT INTO principal_identity (principal_id, provider, subject) VALUES (%s, %s, %s)",
        (pid, ISSUER, subject),
    )
    return pid


def _cleanup(*principal_ids: str) -> None:
    for pid in principal_ids:
        _admin("DELETE FROM principal WHERE id = %s", (pid,))


class _StubClient:
    """Stands in for the authlib client after a successful, validated exchange."""

    def __init__(self, claims: dict | None):
        self._claims = claims

    async def authorize_access_token(self, request):
        return {"userinfo": self._claims} if self._claims is not None else {}

    async def authorize_redirect(self, request, redirect_uri):
        from fastapi.responses import RedirectResponse

        return RedirectResponse(url=f"{ISSUER}/protocol/openid-connect/auth", status_code=302)


def _app(claims: dict | None) -> FastAPI:
    """A minimal app with the auth router and a session, and the OIDC client stubbed."""
    application = FastAPI()
    application.add_middleware(SessionMiddleware, secret_key="test-secret-not-for-use")
    application.include_router(auth.router)

    stub = _StubClient(claims)
    # `_client` is the single place the routes reach for the provider, which is what
    # makes one override enough.
    application.dependency_overrides = {}
    auth._client = lambda request: stub  # type: ignore[assignment]
    return application


@pytest.fixture(autouse=True)
def _restore_client():
    original = auth._client
    yield
    auth._client = original


class TestCallbackEstablishesAnIdentity:
    def test_a_provisioned_subject_logs_in(self):
        subject = f"sub-{uuid.uuid4()}"
        pid = _provisioned_principal(subject)
        try:
            client = TestClient(_app({"sub": subject, "iss": ISSUER}), follow_redirects=False)
            response = client.get("/auth/callback")
            assert response.status_code == 303

            me = client.get("/auth/me")
            assert me.status_code == 200
            assert me.json()["principal_id"] == pid
        finally:
            _cleanup(pid)

    def test_an_unprovisioned_subject_is_refused_and_provisions_nothing(self):
        """ADR-011. The provider authenticated them; we have no record, and login
        does not create one."""
        subject = f"stranger-{uuid.uuid4()}"
        client = TestClient(_app({"sub": subject, "iss": ISSUER}), follow_redirects=False)

        response = client.get("/auth/callback")
        assert response.status_code == 403

        with psycopg.connect(settings().postgres_dsn) as conn:
            n = conn.execute(
                "SELECT count(*) FROM principal_identity WHERE subject = %s", (subject,)
            ).fetchone()[0]
        assert n == 0, "a refused login must not provision an identity"

        # And no session was established.
        assert client.get("/auth/me").status_code == 401

    def test_a_token_without_a_subject_is_refused(self):
        # Every OIDC provider must return `sub`. Its absence means the token is not
        # what we think it is, and continuing would authenticate nobody.
        client = TestClient(_app({"iss": ISSUER}), follow_redirects=False)
        assert client.get("/auth/callback").status_code == 400

    def test_the_issuer_comes_from_the_token_not_the_configuration(self):
        """The stored `(provider, subject)` must be what the provider asserted.

        A principal provisioned against issuer A must not be reachable by a token
        that claims issuer B, even if configuration happens to name A.
        """
        subject = f"sub-{uuid.uuid4()}"
        pid = _provisioned_principal(subject)
        try:
            client = TestClient(
                _app({"sub": subject, "iss": "https://attacker.example/realms/x"}),
                follow_redirects=False,
            )
            assert client.get("/auth/callback").status_code == 403
        finally:
            _cleanup(pid)


class TestWhatTheSessionHolds:
    """The session says who you claim to be. The database says what that lets you do."""

    def test_it_never_holds_a_clearance(self):
        subject = f"sub-{uuid.uuid4()}"
        pid = _provisioned_principal(subject)
        try:
            client = TestClient(_app({"sub": subject, "iss": ISSUER}), follow_redirects=False)
            client.get("/auth/callback")

            # A clearance in a cookie is a snapshot of an authorization decision that
            # keeps being true after the fact stops being. A demoted director would
            # keep reading confidential material until the session expired.
            raw = client.cookies.get("session") or ""
            assert "clearance" not in raw

            body = client.get("/auth/me").json()
            assert "clearance" not in body
        finally:
            _cleanup(pid)

    def test_login_selects_no_workspace(self):
        """ADR-012: a principal may hold several memberships and must not be guessed
        into one. Selection is A4."""
        subject = f"sub-{uuid.uuid4()}"
        pid = _provisioned_principal(subject)
        try:
            client = TestClient(_app({"sub": subject, "iss": ISSUER}), follow_redirects=False)
            client.get("/auth/callback")

            body = client.get("/auth/me").json()
            assert body["workspace_id"] is None
            assert body["workspace_selected"] is False
        finally:
            _cleanup(pid)

    def test_logout_clears_everything(self):
        subject = f"sub-{uuid.uuid4()}"
        pid = _provisioned_principal(subject)
        try:
            client = TestClient(_app({"sub": subject, "iss": ISSUER}), follow_redirects=False)
            client.get("/auth/callback")
            assert client.get("/auth/me").status_code == 200

            assert client.post("/auth/logout").status_code == 200
            assert client.get("/auth/me").status_code == 401
        finally:
            _cleanup(pid)

    def test_me_is_401_without_a_session(self):
        client = TestClient(_app(None), follow_redirects=False)
        assert client.get("/auth/me").status_code == 401


class TestSessionModule:
    """Pure, no HTTP — the read/establish contract."""

    def test_a_partial_session_reads_as_absent(self):
        # A cookie with a principal_id but no provider is not a half-valid login; it
        # is something unexpected, and guessing at its meaning is how an edge case
        # becomes a bypass.
        for partial in (
            {},
            {sess.PRINCIPAL_ID: "x"},
            {sess.PRINCIPAL_ID: "x", sess.PROVIDER: "p"},
            {sess.PROVIDER: "p", sess.SUBJECT: "s"},
        ):
            assert sess.read(partial) is None

    def test_establish_clears_a_previous_workspace_selection(self):
        # A new login is a new session. Carrying a stale selection across one would
        # let a workspace outlive the membership that justified it.
        session = {sess.WORKSPACE_ID: "old-workspace"}
        sess.establish(session, principal_id="p1", provider="i", subject="s")
        assert sess.read(session).workspace_id is None

    def test_clear_empties_unknown_keys_too(self):
        session = {sess.PRINCIPAL_ID: "p", sess.PROVIDER: "i", sess.SUBJECT: "s", "something_else": 1}
        sess.clear(session)
        assert session == {}
