"""The agenda read endpoints (Meridian P3, CP-C — ADR-014).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

Brought forward ahead of `meetings`: the roadmap assumed nothing rendered agenda on
its own, and the codebase disproved it — `meeting-detail` and the dashboard hero both
did, through an `agenda` array the meetings mock invented. Agenda had to become real
before `Meeting` could stop carrying a field the domain never had.
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
from meridian import agenda, meetings
from meridian.api import agenda as agenda_api
from meridian.api import auth, errors

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
    application.include_router(agenda_api.router)
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


def _seed_meeting_with_agenda(workspace_id: str, titles: list[str]) -> tuple[str, list[str]]:
    m = meetings.create_meeting("Board Meeting", workspace_id=workspace_id)
    ids = [
        agenda.create_agenda_item(m.id, t, workspace_id=workspace_id).id for t in titles
    ]
    return m.id, ids


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
        _admin("DELETE FROM agenda_item WHERE workspace_id = %s", (ws,))
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
    def test_lists_a_meetings_agenda_in_position_order(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("agenda")
        _member(pid, ws)
        mid, _ = _seed_meeting_with_agenda(ws, ["Q2 metrics", "Pricing", "Hiring"])
        try:
            body = _client(subject, ws).get("/api/agenda", params={"meeting_id": mid}).json()
            assert [i["title"] for i in body] == ["Q2 metrics", "Pricing", "Hiring"]
            # 1-indexed and contiguous. Unlike board-pack items these are NOT
            # renumbered per caller — agenda is not clearance-filtered — so position
            # is a stable ordinal here rather than a per-reader one.
            assert [i["position"] for i in body] == [1, 2, 3]
        finally:
            _cleanup([pid], [ws])

    def test_meeting_id_is_required(self, restore_client):
        # An agenda item only means anything against its meeting; a workspace-wide
        # list of every item is not a question any surface asks.
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("required")
        _member(pid, ws)
        try:
            assert _client(subject, ws).get("/api/agenda").status_code == 422
        finally:
            _cleanup([pid], [ws])

    def test_fetches_one_item(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("one")
        _member(pid, ws)
        _, ids = _seed_meeting_with_agenda(ws, ["Only item"])
        try:
            response = _client(subject, ws).get(f"/api/agenda/{ids[0]}")
            assert response.status_code == 200
            assert response.json()["title"] == "Only item"
        finally:
            _cleanup([pid], [ws])

    def test_an_unknown_item_is_404(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("404")
        _member(pid, ws)
        try:
            r = _client(subject, ws).get(f"/api/agenda/{uuid.uuid4()}")
            assert r.status_code == 404
            assert r.json()["error"]["code"] == "not_found"
        finally:
            _cleanup([pid], [ws])


class TestIsolationAndAuthorization:
    def test_another_workspaces_agenda_is_invisible(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        mine, theirs = _workspace("mine"), _workspace("theirs")
        _member(pid, mine)
        _seed_meeting_with_agenda(mine, ["Mine"])
        other_mid, other_ids = _seed_meeting_with_agenda(theirs, ["Theirs"])
        try:
            client = _client(subject, mine)
            # The meeting id is not there to find, so the list is empty rather than
            # refused — RLS makes "not yours" and "does not exist" the same answer.
            assert client.get("/api/agenda", params={"meeting_id": other_mid}).json() == []
            assert client.get(f"/api/agenda/{other_ids[0]}").status_code == 404
        finally:
            _cleanup([pid], [mine, theirs])

    def test_unauthenticated_is_401(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        try:
            client = TestClient(_app(subject), follow_redirects=False)
            assert client.get("/api/agenda", params={"meeting_id": str(uuid.uuid4())}).status_code == 401
        finally:
            _cleanup([pid], [])

    def test_revoking_membership_blocks_the_next_read(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("revoke")
        _member(pid, ws)
        mid, _ = _seed_meeting_with_agenda(ws, ["Item"])
        try:
            client = _client(subject, ws)
            assert client.get("/api/agenda", params={"meeting_id": mid}).status_code == 200
            _admin("UPDATE membership SET active = false WHERE principal_id = %s AND workspace_id = %s", (pid, ws))
            assert client.get("/api/agenda", params={"meeting_id": mid}).status_code == 403
        finally:
            _cleanup([pid], [ws])


class TestTheWireShapeMatchesTheFrontendContract:
    def test_the_response_carries_exactly_the_declared_fields(self, restore_client):
        """`lib/agenda.ts` is new in CP-C and replaces an embedded array whose shape
        was wrong three ways: `order` for `position`, `timeboxMins` for
        `duration_minutes`, and no `meeting_id`, `description`, `version` or
        timestamps at all."""
        import re
        from pathlib import Path

        source = Path("frontend/src/lib/agenda.ts").read_text()
        block = re.search(r"export type AgendaItem = \{(.*?)\n\};", source, re.S)
        assert block
        ts_fields = set(re.findall(r"^\s{2}(\w+)\??:", block.group(1), re.M))

        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("shape")
        _member(pid, ws)
        _, ids = _seed_meeting_with_agenda(ws, ["Shape"])
        try:
            body = _client(subject, ws).get(f"/api/agenda/{ids[0]}").json()
            assert set(body) == ts_fields, "the API response and lib/agenda.ts have drifted"
        finally:
            _cleanup([pid], [ws])
