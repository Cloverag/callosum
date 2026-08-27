"""The meetings read endpoints (Meridian P3, CP-C — ADR-014).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

Landed after `agenda`, because `Meeting` carries no agenda in the domain and the
surfaces that render one needed somewhere to fetch it from first.

The property worth testing hardest here is nullability: `scheduled_start` and
`scheduled_end` are `datetime | None` — a draft has no window — and the frontend mock
declared them as required `start`/`end`, so anything doing `new Date(m.start)` on a
draft was building an Invalid Date.
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
from meridian import meetings
from meridian.api import auth, errors
from meridian.api import meetings as meetings_api

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
    application.include_router(meetings_api.router)
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


def _seed_meeting(workspace_id: str, title: str, *, scheduled: bool = True) -> str:
    from datetime import datetime, timedelta, timezone

    if scheduled:
        start = datetime(2026, 7, 28, 9, 0, tzinfo=timezone.utc)
        m = meetings.create_meeting(
            title, workspace_id=workspace_id, scheduled_start=start, scheduled_end=start + timedelta(hours=2)
        )
    else:
        m = meetings.create_meeting(title, workspace_id=workspace_id)
    return m.id


def _cleanup(principal_ids: list[str], workspace_ids: list[str]) -> None:
    for ws in workspace_ids:
        # Before every other delete below. `audit_event` references both
        # `workspace(id)` and `principal(id)` ON DELETE RESTRICT (0016, deliberately),
        # so once any route in this file is audited, the workspace cannot be dropped
        # until its trail is. Issue #170.
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
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
    def test_lists_meetings_including_undated_drafts(self, restore_client):
        """Undated meetings are real records and the list returns them.

        Hiding them here to suit the calendar would make the meetings list disagree
        with the database. The calendar narrows instead, at the point where having a
        date actually matters.
        """
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("list")
        _member(pid, ws)
        _seed_meeting(ws, "Scheduled one")
        _seed_meeting(ws, "Undated draft", scheduled=False)
        try:
            body = _client(subject, ws).get("/api/meetings").json()
            assert sorted(m["title"] for m in body) == ["Scheduled one", "Undated draft"]
            undated = next(m for m in body if m["title"] == "Undated draft")
            # The nullability the mock's required `start` field concealed.
            assert undated["scheduled_start"] is None
            assert undated["scheduled_end"] is None
        finally:
            _cleanup([pid], [ws])

    def test_filters_by_status(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("filter")
        _member(pid, ws)
        _seed_meeting(ws, "A draft", scheduled=False)
        try:
            client = _client(subject, ws)
            assert len(client.get("/api/meetings", params={"status": "draft"}).json()) == 1
            assert client.get("/api/meetings", params={"status": "completed"}).json() == []
        finally:
            _cleanup([pid], [ws])

    def test_an_unknown_status_is_422(self, restore_client):
        # `review` and `archived` were in the frontend type until #47; the domain has
        # never accepted either, and this is what that refusal looks like over HTTP.
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("422")
        _member(pid, ws)
        try:
            r = _client(subject, ws).get("/api/meetings", params={"status": "archived"})
            assert r.status_code == 422
            assert r.json()["error"]["code"] == "invalid"
        finally:
            _cleanup([pid], [ws])

    def test_get_one(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("one")
        _member(pid, ws)
        mid = _seed_meeting(ws, "Only meeting")
        try:
            assert _client(subject, ws).get(f"/api/meetings/{mid}").json()["title"] == "Only meeting"
        finally:
            _cleanup([pid], [ws])


class TestIsolationAndAuthorization:
    def test_another_workspaces_meeting_is_not_found(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        mine, theirs = _workspace("mine"), _workspace("theirs")
        _member(pid, mine)
        _seed_meeting(mine, "Mine")
        other = _seed_meeting(theirs, "Theirs")
        try:
            client = _client(subject, mine)
            assert [m["title"] for m in client.get("/api/meetings").json()] == ["Mine"]
            assert client.get(f"/api/meetings/{other}").status_code == 404
        finally:
            _cleanup([pid], [mine, theirs])

    def test_revoking_membership_blocks_the_next_read(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("revoke")
        _member(pid, ws)
        _seed_meeting(ws, "A meeting")
        try:
            client = _client(subject, ws)
            assert client.get("/api/meetings").status_code == 200
            _admin("UPDATE membership SET active = false WHERE principal_id = %s AND workspace_id = %s", (pid, ws))
            assert client.get("/api/meetings").status_code == 403
        finally:
            _cleanup([pid], [ws])


class TestTheWireShapeMatchesTheFrontendContract:
    def test_the_response_carries_exactly_the_declared_fields(self, restore_client):
        """lib/meetings.ts lost `objectives`, `sensitivity` and `agenda` — fields the
        domain never had — and renamed `start`/`end` to the domain's names."""
        import re
        from pathlib import Path

        source = Path("frontend/src/lib/meetings.ts").read_text()
        block = re.search(r"export type Meeting = \{(.*?)\n\};", source, re.S)
        assert block
        ts_fields = set(re.findall(r"^\s{2}(\w+)\??:", block.group(1), re.M))

        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("shape")
        _member(pid, ws)
        mid = _seed_meeting(ws, "Shape")
        try:
            body = _client(subject, ws).get(f"/api/meetings/{mid}").json()
            assert set(body) == ts_fields, "the API response and lib/meetings.ts have drifted"
            for gone in ("objectives", "sensitivity", "agenda"):
                assert gone not in body
        finally:
            _cleanup([pid], [ws])
