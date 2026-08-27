"""The resolutions read endpoints (Meridian P3, CP-B — ADR-014).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

This is the first vertical slice, so these tests establish what every later module's
tests have to prove: that the workspace comes from the session and nowhere else, that
authorization is re-derived per request, and that domain exceptions arrive as the right
status without the route restating any of them.
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
from meridian import decisions, meetings, resolutions
from meridian.api import auth, errors
from meridian.api import resolutions as resolutions_api

pytestmark = pytest.mark.integration

ISSUER = "https://keycloak.example/realms/meridian"


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
    application.include_router(resolutions_api.router)
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
        "INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, 'director', 2)",
        (pid, f"API User {pid[:6]}"),
    )
    _admin(
        "INSERT INTO principal_identity (principal_id, provider, subject) VALUES (%s, %s, %s)",
        (pid, ISSUER, subject),
    )
    return pid


def _member(principal_id: str, workspace_id: str, clearance: int = 2) -> None:
    _admin(
        "INSERT INTO membership (principal_id, workspace_id, role, clearance, active)"
        " VALUES (%s, %s, 'director', %s, true)",
        (principal_id, workspace_id, clearance),
    )


def _seed_resolution(workspace_id: str, title: str = "Resolution 1") -> str:
    m = meetings.create_meeting("Board Meeting", workspace_id=workspace_id)
    d = decisions.create_decision(m.id, "A decision", workspace_id=workspace_id)
    r = resolutions.create_resolution(d.id, title, "RESOLVED THAT …", workspace_id=workspace_id)
    return r.id


def _cleanup(principal_ids: list[str], workspace_ids: list[str]) -> None:
    for ws in workspace_ids:
        # Before every other delete below. `audit_event` references both
        # `workspace(id)` and `principal(id)` ON DELETE RESTRICT (0016, deliberately),
        # so once any route in this file is audited, the workspace cannot be dropped
        # until its trail is. Issue #170.
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM resolution_vote WHERE workspace_id = %s", (ws,))
        _admin("UPDATE resolution SET superseded_by_id = NULL WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM resolution WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM decision WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM meeting WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM membership WHERE workspace_id = %s", (ws,))
    for pid in principal_ids:
        _admin("DELETE FROM principal WHERE id = %s", (pid,))
    for ws in workspace_ids:
        _admin("DELETE FROM workspace WHERE id = %s", (ws,))


def _client(subject: str, workspace_id: str | None) -> TestClient:
    client = TestClient(_app(subject), follow_redirects=False)
    assert client.get("/auth/callback").status_code == 303
    if workspace_id is not None:
        assert client.post("/auth/workspace", json={"workspace_id": workspace_id}).status_code == 200
    return client


class TestReads:
    def test_lists_resolutions_in_the_session_workspace(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("list")
        _member(pid, ws)
        rid = _seed_resolution(ws, "Resolution 2026-04")
        try:
            response = _client(subject, ws).get("/api/resolutions")
            assert response.status_code == 200
            body = response.json()
            assert [r["id"] for r in body] == [rid]
            assert body[0]["title"] == "Resolution 2026-04"
        finally:
            _cleanup([pid], [ws])

    def test_fetches_one_resolution_with_its_votes(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("get")
        _member(pid, ws)
        rid = _seed_resolution(ws)
        try:
            response = _client(subject, ws).get(f"/api/resolutions/{rid}")
            assert response.status_code == 200
            assert response.json()["id"] == rid
            assert response.json()["votes"] == []
        finally:
            _cleanup([pid], [ws])

    def test_filters_by_status(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("filter")
        _member(pid, ws)
        _seed_resolution(ws)
        try:
            client = _client(subject, ws)
            assert len(client.get("/api/resolutions", params={"status": "draft"}).json()) == 1
            assert client.get("/api/resolutions", params={"status": "adopted"}).json() == []
        finally:
            _cleanup([pid], [ws])


class TestTheWorkspaceComesFromTheSession:
    def test_a_resolution_in_another_workspace_is_not_found(self, restore_client):
        """The isolation test that matters.

        Not because the endpoint checks — because RLS means the row is not there to
        find. "Does not exist" and "exists but is not yours" are the same answer.
        """
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        mine, theirs = _workspace("mine"), _workspace("theirs")
        _member(pid, mine)
        _seed_resolution(mine, "Mine")
        other_rid = _seed_resolution(theirs, "Theirs")
        try:
            client = _client(subject, mine)

            assert [r["title"] for r in client.get("/api/resolutions").json()] == ["Mine"]
            assert client.get(f"/api/resolutions/{other_rid}").status_code == 404
        finally:
            _cleanup([pid], [mine, theirs])

    def test_a_workspace_id_query_parameter_is_ignored(self, restore_client):
        """Belt and braces alongside the schema guard.

        The endpoint declares no such parameter, so FastAPI drops it — but asserting
        it makes the intent explicit: supplying one changes nothing, rather than
        being rejected in a way someone might later "fix" by accepting it.
        """
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        mine, theirs = _workspace("mine"), _workspace("theirs")
        _member(pid, mine)
        _seed_resolution(mine, "Mine")
        _seed_resolution(theirs, "Theirs")
        try:
            client = _client(subject, mine)
            smuggled = client.get("/api/resolutions", params={"workspace_id": theirs})
            assert smuggled.status_code == 200
            assert [r["title"] for r in smuggled.json()] == ["Mine"]
        finally:
            _cleanup([pid], [mine, theirs])


class TestAuthorizationIsEnforcedPerRequest:
    def test_unauthenticated_is_401(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        try:
            client = TestClient(_app(subject), follow_redirects=False)
            assert client.get("/api/resolutions").status_code == 401
        finally:
            _cleanup([pid], [])

    def test_authenticated_without_a_workspace_is_409(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        try:
            assert _client(subject, None).get("/api/resolutions").status_code == 409
        finally:
            _cleanup([pid], [])

    def test_revoking_membership_blocks_the_next_read(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("revoke")
        _member(pid, ws)
        _seed_resolution(ws)
        try:
            client = _client(subject, ws)
            assert client.get("/api/resolutions").status_code == 200

            _admin(
                "UPDATE membership SET active = false WHERE principal_id = %s AND workspace_id = %s",
                (pid, ws),
            )
            # Same cookie, next request. Nothing was cached, so nothing needs clearing.
            assert client.get("/api/resolutions").status_code == 403
        finally:
            _cleanup([pid], [ws])


class TestErrorsComeFromTheTaxonomy:
    """The route restates no status. These prove the central handler is wired."""

    def test_an_unknown_id_is_404(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("404")
        _member(pid, ws)
        try:
            response = _client(subject, ws).get(f"/api/resolutions/{uuid.uuid4()}")
            assert response.status_code == 404
            assert response.json()["error"]["code"] == "not_found"
        finally:
            _cleanup([pid], [ws])

    def test_an_unknown_status_filter_is_422(self, restore_client):
        # `list_resolutions` raises ResolutionValidationError; the endpoint says
        # nothing about it and the taxonomy turns it into 422.
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("422")
        _member(pid, ws)
        try:
            response = _client(subject, ws).get("/api/resolutions", params={"status": "ratified"})
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "invalid"
        finally:
            _cleanup([pid], [ws])


class TestTheWireShapeMatchesTheFrontendContract:
    """Cross-language drift check.

    `frontend/src/lib/resolutions.ts` was written to mirror the Python dataclasses
    field-for-field, which is what makes the CP-B mock swap a change of transport and
    nothing else. Nothing enforced that until now — so this reads the TypeScript type
    and compares it to what the endpoint actually serialises.
    """

    @staticmethod
    def _ts_fields(type_name: str) -> set[str]:
        import re
        from pathlib import Path

        source = Path("frontend/src/lib/resolutions.ts").read_text()
        block = re.search(rf"export type {type_name} = \{{(.*?)\n\}};", source, re.S)
        assert block, f"{type_name} not found in resolutions.ts"
        # Field lines only: `name: type;` or `name?: type;`, ignoring comments.
        return set(re.findall(r"^\s{2}(\w+)\??:", block.group(1), re.M))

    def test_the_response_carries_exactly_the_declared_fields(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("shape")
        _member(pid, ws)
        rid = _seed_resolution(ws)
        try:
            body = _client(subject, ws).get(f"/api/resolutions/{rid}").json()
            assert set(body) == self._ts_fields("Resolution"), (
                "the API response and lib/resolutions.ts have drifted"
            )
        finally:
            _cleanup([pid], [ws])

    def test_the_vote_shape_matches_too(self, restore_client):
        import dataclasses

        from meridian.resolutions import ResolutionVote

        python_fields = {f.name for f in dataclasses.fields(ResolutionVote)}
        assert python_fields == self._ts_fields("ResolutionVote")

    def test_timestamps_serialise_as_iso_strings(self, restore_client):
        # The TS type declares `created_at: string // ISO`. A datetime that arrived as
        # anything else would typecheck in Python and break in the browser.
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("iso")
        _member(pid, ws)
        rid = _seed_resolution(ws)
        try:
            body = _client(subject, ws).get(f"/api/resolutions/{rid}").json()
            assert isinstance(body["created_at"], str)
            assert body["created_at"][4] == "-" and "T" in body["created_at"]
            assert body["adopted_at"] is None  # a draft has none, and null survives
        finally:
            _cleanup([pid], [ws])
