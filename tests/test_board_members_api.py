"""The board-directory read endpoints (Meridian P3, CP-C — ADR-014).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

The first module to follow CP-B's pattern, so these prove the same three things the
resolutions tests do — session-derived workspace, per-request authorization, statuses
from the taxonomy — plus the one thing specific to this aggregate: `active` is a
tri-state, and the wire has to carry all three states rather than the two the frontend
mock exposed.
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
from meridian import board_members
from meridian.api import auth, errors
from meridian.api import board_members as board_members_api

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
    application.include_router(board_members_api.router)
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


def _seed_member(workspace_id: str, name: str, *, role: str = "director", active: bool = True) -> str:
    member = board_members.create_member(name, role, workspace_id=workspace_id)
    if not active:
        board_members.deactivate_member(member.id, expected_version=1, workspace_id=workspace_id)
    return member.id


def _cleanup(principal_ids: list[str], workspace_ids: list[str]) -> None:
    for ws in workspace_ids:
        # First, and before the principals below. `audit_event` references both
        # `workspace(id)` and `principal(id)` ON DELETE RESTRICT (0016, deliberately —
        # an audit log a workspace deletion silently empties is not an audit log).
        #
        # The general consequence, which every newly audited route inherits: once any
        # audit event exists for a workspace, that workspace cannot be deleted until
        # the trail is. This teardown was written when board members were unaudited,
        # so it did not need the line; `test_documents_api._cleanup` already has it
        # because documents were audited before it was written.
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM board_member WHERE workspace_id = %s", (ws,))
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
    def test_lists_active_members_by_default(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("dir")
        _member(pid, ws)
        _seed_member(ws, "Serving Director")
        _seed_member(ws, "Departed Director", active=False)
        try:
            body = _client(subject, ws).get("/api/board-members").json()
            assert [m["full_name"] for m in body] == ["Serving Director"]
        finally:
            _cleanup([pid], [ws])

    def test_active_all_returns_everyone(self, restore_client):
        """What a surface rendering history needs.

        A departed director still cast the votes on record; filtering them out makes
        historic votes render as unresolvable, which reads as data loss.
        """
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("all")
        _member(pid, ws)
        _seed_member(ws, "Serving Director")
        _seed_member(ws, "Departed Director", active=False)
        try:
            body = _client(subject, ws).get("/api/board-members", params={"active": "all"}).json()
            assert sorted(m["full_name"] for m in body) == ["Departed Director", "Serving Director"]
        finally:
            _cleanup([pid], [ws])

    def test_active_false_returns_departed_only(self, restore_client):
        """The third state the frontend's `include_inactive` flag could not express."""
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("departed")
        _member(pid, ws)
        _seed_member(ws, "Serving Director")
        _seed_member(ws, "Departed Director", active=False)
        try:
            body = _client(subject, ws).get("/api/board-members", params={"active": "false"}).json()
            assert [m["full_name"] for m in body] == ["Departed Director"]
            assert body[0]["active"] is False
        finally:
            _cleanup([pid], [ws])

    def test_filters_by_role(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("role")
        _member(pid, ws)
        _seed_member(ws, "A Director", role="director")
        _seed_member(ws, "An Observer", role="observer")
        try:
            body = _client(subject, ws).get("/api/board-members", params={"role": "observer"}).json()
            assert [m["full_name"] for m in body] == ["An Observer"]
        finally:
            _cleanup([pid], [ws])

    def test_get_returns_an_inactive_member(self, restore_client):
        # Mirrors the domain: historical votes resolve through this lookup, so a
        # departed director must not become unresolvable.
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("get")
        _member(pid, ws)
        mid = _seed_member(ws, "Departed Director", active=False)
        try:
            response = _client(subject, ws).get(f"/api/board-members/{mid}")
            assert response.status_code == 200
            assert response.json()["active"] is False
        finally:
            _cleanup([pid], [ws])

    def test_an_unknown_active_value_is_rejected_by_the_schema(self, restore_client):
        # A Literal, so FastAPI refuses it before the domain sees it.
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("bad")
        _member(pid, ws)
        try:
            assert _client(subject, ws).get(
                "/api/board-members", params={"active": "maybe"}
            ).status_code == 422
        finally:
            _cleanup([pid], [ws])


class TestIsolationAndAuthorization:
    def test_a_member_of_another_workspace_is_not_found(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        mine, theirs = _workspace("mine"), _workspace("theirs")
        _member(pid, mine)
        _seed_member(mine, "Mine")
        other = _seed_member(theirs, "Theirs")
        try:
            client = _client(subject, mine)
            assert [m["full_name"] for m in client.get("/api/board-members").json()] == ["Mine"]
            assert client.get(f"/api/board-members/{other}").status_code == 404
        finally:
            _cleanup([pid], [mine, theirs])

    def test_unauthenticated_is_401(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        try:
            client = TestClient(_app(subject), follow_redirects=False)
            assert client.get("/api/board-members").status_code == 401
        finally:
            _cleanup([pid], [])

    def test_revoking_membership_blocks_the_next_read(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("revoke")
        _member(pid, ws)
        _seed_member(ws, "Someone")
        try:
            client = _client(subject, ws)
            assert client.get("/api/board-members").status_code == 200
            _admin(
                "UPDATE membership SET active = false WHERE principal_id = %s AND workspace_id = %s",
                (pid, ws),
            )
            assert client.get("/api/board-members").status_code == 403
        finally:
            _cleanup([pid], [ws])


class TestTheWireShapeMatchesTheFrontendContract:
    @staticmethod
    def _ts_fields(type_name: str) -> set[str]:
        import re
        from pathlib import Path

        source = Path("frontend/src/lib/board-members.ts").read_text()
        block = re.search(rf"export type {type_name} = \{{(.*?)\n\}};", source, re.S)
        assert block, f"{type_name} not found in board-members.ts"
        return set(re.findall(r"^\s{2}(\w+)\??:", block.group(1), re.M))

    def test_the_response_carries_exactly_the_declared_fields(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("shape")
        _member(pid, ws)
        mid = _seed_member(ws, "Shape Director")
        try:
            body = _client(subject, ws).get(f"/api/board-members/{mid}").json()
            assert set(body) == self._ts_fields("BoardMember"), (
                "the API response and lib/board-members.ts have drifted"
            )
        finally:
            _cleanup([pid], [ws])

    def test_the_directory_carries_no_clearance(self, restore_client):
        """Clearance belongs to `membership`. Two sources of truth is how RBAC gets
        bypassed, and CP5b had to unwind exactly that."""
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("noclearance")
        _member(pid, ws)
        mid = _seed_member(ws, "No Clearance Here")
        try:
            body = _client(subject, ws).get(f"/api/board-members/{mid}").json()
            assert "clearance" not in body
            assert "sensitivity" not in body
        finally:
            _cleanup([pid], [ws])
