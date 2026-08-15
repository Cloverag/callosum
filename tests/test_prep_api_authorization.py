"""Meeting-preparation endpoints re-derive authorization on every request (P3, ADR-012).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

---------------------------------------------------------------------------
THE DEFECT THESE TESTS EXIST FOR
---------------------------------------------------------------------------
All three handlers took ``current_session`` + ``current_workspace``. Neither checks
membership — ``current_session`` says who the caller claims to be, and
``current_workspace`` only validates that the id in the cookie is a well-formed UUID.
Only ``current_principal`` reaches ``resolve_principal_by_id()``, which JOINs to an
**active** membership.

So a principal whose membership was revoked kept working here until their session
expired, up to ``MAX_SESSION_LIFETIME_SECONDS`` (24 hours) — including on
``publish-preread``, which publishes a board pack and attributes it to them.

**The shape of the test matters more than its existence.** Asserting that a member
gets 200 would have passed before the fix. The load-bearing case is *revoke after
selection*: sign in, select the workspace legitimately, have membership revoked, and
then call. That is the sequence ADR-012 exists for, and the only one that fails
against the old code.

The router's entire previous coverage was ``test_prep_api_router_registered``, which
asserts a decorator ran at import time and never calls a handler — the same shape of
non-coverage that let ``conflicts.py`` return 500 for three days (#130).
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

from callosum.config import settings
from meridian import meetings
from meridian.api import auth, errors
from meridian.api import prep as prep_api

pytestmark = pytest.mark.integration

ISSUER = "https://keycloak.example/realms/meridian"
DIRECTOR_CLEARANCE = 2


def _admin(sql: str, params: tuple = ()) -> None:
    with psycopg.connect(settings().postgres_dsn) as conn:
        conn.execute(sql, params)
        conn.commit()


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
    application.include_router(prep_api.router)
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


def _principal_with_identity(subject: str) -> str:
    pid = str(uuid.uuid4())
    _admin(
        "INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, 'director', %s)",
        (pid, f"Prep User {pid[:6]}", DIRECTOR_CLEARANCE),
    )
    _admin(
        "INSERT INTO principal_identity (principal_id, provider, subject) VALUES (%s, %s, %s)",
        (pid, ISSUER, subject),
    )
    return pid


def _member(principal_id: str, workspace_id: str) -> None:
    _admin(
        "INSERT INTO membership (principal_id, workspace_id, role, clearance, active)"
        " VALUES (%s, %s, 'director', %s, true)",
        (principal_id, workspace_id, DIRECTOR_CLEARANCE),
    )


def _deactivate_membership(principal_id: str, workspace_id: str) -> None:
    """Revocation as the product models it — the row stays, `active` goes false."""
    _admin(
        "UPDATE membership SET active = false WHERE principal_id = %s AND workspace_id = %s",
        (principal_id, workspace_id),
    )


def _delete_membership(principal_id: str, workspace_id: str) -> None:
    """The harder revocation: the row is gone, not flagged."""
    _admin(
        "DELETE FROM membership WHERE principal_id = %s AND workspace_id = %s",
        (principal_id, workspace_id),
    )


def _cleanup(principal_ids: list[str], workspace_ids: list[str]) -> None:
    for ws in workspace_ids:
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM agenda_item WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM board_pack WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM meeting WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM membership WHERE workspace_id = %s", (ws,))
    for pid in principal_ids:
        _admin("DELETE FROM principal WHERE id = %s", (pid,))
    for ws in workspace_ids:
        _admin("DELETE FROM workspace WHERE id = %s", (ws,))


def _signed_in(label: str) -> tuple[TestClient, str, str, str]:
    """A client that has signed in AND legitimately selected its workspace.

    Selection happens while the membership is valid, which is what makes the
    revocation tests below meaningful: the cookie is genuine, not forged.
    """
    subject = f"sub-{uuid.uuid4()}"
    pid = _principal_with_identity(subject)
    ws = _workspace(label)
    _member(pid, ws)

    client = TestClient(_app(subject), follow_redirects=False)
    assert client.get("/auth/callback").status_code == 303
    assert client.post("/auth/workspace", json={"workspace_id": ws}).status_code == 200

    meeting = meetings.create_meeting("Prep Test Meeting", workspace_id=ws, created_by=pid)
    return client, pid, ws, meeting.id


def _endpoints(meeting_id: str) -> list[tuple[str, str]]:
    """Every route on this router, so a new one cannot quietly skip these tests."""
    return [
        ("GET", f"/api/meetings/{meeting_id}/readiness"),
        ("GET", f"/api/meetings/{meeting_id}/agenda-suggestions"),
        ("POST", f"/api/meetings/{meeting_id}/publish-preread"),
    ]


def _call(client: TestClient, method: str, path: str):
    return client.get(path) if method == "GET" else client.post(path)


class TestAnActiveMemberIsServed:
    """The filter must remove callers, not the feature.

    These would have passed before the fix too. They are here so a later change that
    makes the authorization stricter cannot pass by refusing everyone.
    """

    def test_reads_succeed(self, restore_client):
        client, pid, ws, meeting_id = _signed_in("active_reads")
        try:
            assert client.get(f"/api/meetings/{meeting_id}/readiness").status_code == 200
            assert (
                client.get(f"/api/meetings/{meeting_id}/agenda-suggestions").status_code == 200
            )
        finally:
            _cleanup([pid], [ws])

    def test_the_write_is_reachable(self, restore_client):
        """`publish-preread` 400s without a pack to publish — not 401, 403 or 500.

        A 400 proves the request reached the domain, which is what distinguishes
        "authorized and there is nothing to publish" from "refused at the door".
        """
        client, pid, ws, meeting_id = _signed_in("active_write")
        try:
            res = client.post(f"/api/meetings/{meeting_id}/publish-preread")
            assert res.status_code == 400
        finally:
            _cleanup([pid], [ws])


class TestRevocationTakesEffectOnTheNextRequest:
    """The regression this PR exists for. Every case here fails against the old code."""

    @pytest.mark.parametrize("method,path_tmpl", [
        ("GET", "readiness"), ("GET", "agenda-suggestions"), ("POST", "publish-preread"),
    ])
    def test_a_deactivated_membership_is_refused(self, restore_client, method, path_tmpl):
        client, pid, ws, meeting_id = _signed_in("deactivated")
        try:
            _deactivate_membership(pid, ws)
            res = _call(client, method, f"/api/meetings/{meeting_id}/{path_tmpl}")
            assert res.status_code == 403, (
                f"{method} {path_tmpl} still served a revoked membership — the session "
                f"cookie outlived the authorization that justified it."
            )
        finally:
            _cleanup([pid], [ws])

    @pytest.mark.parametrize("method,path_tmpl", [
        ("GET", "readiness"), ("GET", "agenda-suggestions"), ("POST", "publish-preread"),
    ])
    def test_a_deleted_membership_is_refused(self, restore_client, method, path_tmpl):
        """Deletion rather than deactivation — `active = false` is not the only revocation."""
        client, pid, ws, meeting_id = _signed_in("deleted")
        try:
            _delete_membership(pid, ws)
            res = _call(client, method, f"/api/meetings/{meeting_id}/{path_tmpl}")
            assert res.status_code == 403
        finally:
            _cleanup([pid], [ws])

    def test_the_write_does_not_publish_after_revocation(self, restore_client):
        """403 is the response; *not having published* is the property that matters.

        A refusal that still performed the write would satisfy a status-code assertion
        and be worthless.
        """
        client, pid, ws, meeting_id = _signed_in("no_publish")
        try:
            _deactivate_membership(pid, ws)
            client.post(f"/api/meetings/{meeting_id}/publish-preread")

            with psycopg.connect(settings().postgres_dsn) as conn:
                published = conn.execute(
                    "SELECT count(*) AS n FROM board_pack"
                    " WHERE meeting_id = %s AND status = 'published'",
                    (uuid.UUID(meeting_id),),
                ).fetchone()[0]
            assert published == 0
        finally:
            _cleanup([pid], [ws])


class TestTheRefusalLeaksNothing:
    def test_the_403_does_not_say_why(self, restore_client):
        """`PrincipalNotFound` conflates "never a member", "revoked" and "not yours".

        Echoing which one applies would rebuild the membership oracle that conflation
        exists to prevent. `deps.current_principal` returns a fixed string; this asserts
        the fixed string survives the trip through the error taxonomy.
        """
        client, pid, ws, meeting_id = _signed_in("uniform_403")
        try:
            _deactivate_membership(pid, ws)
            res = client.get(f"/api/meetings/{meeting_id}/readiness")

            assert res.status_code == 403
            body = res.json()
            assert body["error"]["code"] == "forbidden"
            assert body["error"]["detail"] == "Not available to you."
            for leak in ("membership", "revoked", "inactive", "active", ws, pid):
                assert leak not in res.text
        finally:
            _cleanup([pid], [ws])


class TestTheOtherRefusals:
    def test_no_session_is_401(self, restore_client):
        """Unauthenticated is distinct from unauthorized, and must not be a 403."""
        _, pid, ws, meeting_id = _signed_in("anon")
        try:
            anon = TestClient(_app("sub-nobody"), follow_redirects=False)
            for method, path in _endpoints(meeting_id):
                assert _call(anon, method, path).status_code == 401
        finally:
            _cleanup([pid], [ws])

    def test_authenticated_without_a_workspace_is_409(self, restore_client):
        """409, not 401 — the caller is signed in, they simply have not chosen yet.

        Answering 401 here would send a logged-in client back to log in and loop.
        """
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("noselect")
        _member(pid, ws)
        meeting = meetings.create_meeting("Unselected", workspace_id=ws, created_by=pid)
        try:
            client = TestClient(_app(subject), follow_redirects=False)
            assert client.get("/auth/callback").status_code == 303  # no /auth/workspace
            for method, path in _endpoints(meeting.id):
                assert _call(client, method, path).status_code == 409
        finally:
            _cleanup([pid], [ws])


def test_every_route_on_this_router_depends_on_current_principal():
    """A structural guard, because the per-route tests above only cover today's routes.

    A fourth endpoint added with `current_session` would be a silent reopening of this
    defect: it would work, return the right data, and skip the membership check. This
    reads the signatures instead of trusting that whoever adds it read the docstring.
    """
    import inspect
    import typing

    from meridian.api import deps

    handlers = [
        prep_api.get_readiness,
        prep_api.get_agenda_suggestions,
        prep_api.publish_preread,
    ]
    routes = {r.endpoint for r in prep_api.router.routes}
    assert routes == set(handlers), (
        "a route on the prep router is not in this test's handler list — add it, and "
        "give it the authorization tests above"
    )

    def _depends_on_current_principal(fn) -> bool:
        """Look for the actual dependency, not the alias's name.

        `deps.CurrentPrincipal` is `Annotated[Principal, Depends(current_principal)]`,
        and the alias name does not survive into the runtime object — a string match on
        "CurrentPrincipal" finds nothing. What identifies it is the `Depends` marker in
        the annotation metadata pointing at `deps.current_principal`, which is also what
        FastAPI itself resolves, so this asserts the thing that actually runs.
        """
        for annotation in inspect.get_annotations(fn, eval_str=False).values():
            for meta in getattr(annotation, "__metadata__", ()):
                if getattr(meta, "dependency", None) is deps.current_principal:
                    return True
        return False

    for fn in handlers:
        assert _depends_on_current_principal(fn), (
            f"{fn.__name__} does not depend on deps.current_principal, so nothing on that "
            f"path re-validates membership"
        )
