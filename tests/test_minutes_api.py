"""The minutes read endpoints (Meridian P3, CP-C — ADR-014).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

The inverse of packs in one important way: **minutes take no clearance at all**. The
table has no `sensitivity` column and no domain function accepts one, so there is
nothing to filter by and no parameter to withhold. Whether that is right is issue #49;
these tests pin what the contract *is*, not what it should become.

`meeting_id` is required, mirroring `list_minutes`. The frontend mock made it optional
and invented a status filter — offering a capability the backend cannot honour.
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
from meridian import meetings, minutes
from meridian.api import auth, errors
from meridian.api import minutes as minutes_api

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
    application.include_router(minutes_api.router)
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


def _member(principal_id: str, workspace_id: str, clearance: int = 4) -> None:
    _admin(
        "INSERT INTO membership (principal_id, workspace_id, role, clearance, active)"
        " VALUES (%s, %s, 'director', %s, true)",
        (principal_id, workspace_id, clearance),
    )


def _seed_minutes(workspace_id: str, bodies: list[str]) -> tuple[str, list[str]]:
    """A live meeting with one or more minutes versions.

    Minutes require an `in_progress` or `completed` meeting — they are written during
    or after one and cannot exist before it, which is the inverse of the board-pack
    rule. So the meeting has to be driven forward before any of this is legal.
    """
    from datetime import datetime, timedelta, timezone

    start = datetime(2026, 7, 28, 9, 0, tzinfo=timezone.utc)
    m = meetings.create_meeting(
        "Board Meeting",
        workspace_id=workspace_id,
        scheduled_start=start,
        scheduled_end=start + timedelta(hours=2),
    )
    m = meetings.transition_status(m.id, meetings.SCHEDULED, expected_version=1, workspace_id=workspace_id)
    m = meetings.transition_status(m.id, meetings.IN_PROGRESS, expected_version=m.version, workspace_id=workspace_id)
    ids = [minutes.create_minutes(m.id, b, workspace_id=workspace_id).id for b in bodies]
    return m.id, ids


def _cleanup(principal_ids: list[str], workspace_ids: list[str]) -> None:
    for ws in workspace_ids:
        # Before every other delete below. `audit_event` references both
        # `workspace(id)` and `principal(id)` ON DELETE RESTRICT (0016, deliberately),
        # so once any route in this file is audited, the workspace cannot be dropped
        # until its trail is. Issue #170.
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
        _admin("UPDATE minutes SET superseded_by_id = NULL WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM minutes WHERE workspace_id = %s", (ws,))
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
    def test_lists_every_version_for_a_meeting(self, restore_client):
        """The correction trail is the point.

        A list showing only the standing record would hide exactly what a board needs
        to reconstruct — that the minutes were amended, and to what.
        """
        ws = _workspace("list")
        mid, ids = _seed_minutes(ws, ["First record", "Second record"])
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        _member(pid, ws)
        try:
            body = _client(subject, ws).get("/api/minutes", params={"meeting_id": mid}).json()
            assert len(body) == 2
            assert set(m["id"] for m in body) == set(ids)
        finally:
            _cleanup([pid], [ws])

    def test_meeting_id_is_required(self, restore_client):
        # The mock made it optional; list_minutes never did.
        ws = _workspace("req")
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        _member(pid, ws)
        try:
            assert _client(subject, ws).get("/api/minutes").status_code == 422
        finally:
            _cleanup([pid], [ws])

    def test_get_one(self, restore_client):
        ws = _workspace("one")
        _, ids = _seed_minutes(ws, ["Only record"])
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        _member(pid, ws)
        try:
            body = _client(subject, ws).get(f"/api/minutes/{ids[0]}").json()
            assert body["body"] == "Only record"
            assert body["status"] == "draft"
        finally:
            _cleanup([pid], [ws])

    def test_an_unknown_id_is_404(self, restore_client):
        ws = _workspace("404")
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        _member(pid, ws)
        try:
            r = _client(subject, ws).get(f"/api/minutes/{uuid.uuid4()}")
            assert r.status_code == 404
            assert r.json()["error"]["code"] == "not_found"
        finally:
            _cleanup([pid], [ws])


class TestThereIsNoClearanceHere:
    def test_two_clearances_see_identical_minutes(self, restore_client):
        """The inverse of the packs test, and it has to be stated.

        Packs filter by clearance; minutes do not, because the table has no
        sensitivity column. A reader at clearance 1 and a reader at clearance 4 get
        the same bytes — which is the contract today, and exactly what issue #49 asks
        whether we want.
        """
        ws = _workspace("noclr")
        mid, _ = _seed_minutes(ws, ["Compensation was discussed at length."])
        hi_subject, lo_subject = f"sub-{uuid.uuid4()}", f"sub-{uuid.uuid4()}"
        hi, lo = _principal_with_identity(hi_subject), _principal_with_identity(lo_subject)
        _member(hi, ws, clearance=4)
        _member(lo, ws, clearance=1)
        try:
            founder = _client(hi_subject, ws).get("/api/minutes", params={"meeting_id": mid}).json()
            investor = _client(lo_subject, ws).get("/api/minutes", params={"meeting_id": mid}).json()
            assert founder == investor
        finally:
            _cleanup([hi, lo], [ws])

    def test_the_response_carries_no_access_level(self, restore_client):
        ws = _workspace("nofield")
        _, ids = _seed_minutes(ws, ["Body"])
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        _member(pid, ws)
        try:
            body = _client(subject, ws).get(f"/api/minutes/{ids[0]}").json()
            for absent in ("clearance", "sensitivity", "withheld"):
                assert absent not in body
        finally:
            _cleanup([pid], [ws])


class TestIsolation:
    def test_another_workspaces_minutes_are_not_found(self, restore_client):
        mine, theirs = _workspace("mine"), _workspace("theirs")
        _seed_minutes(mine, ["Mine"])
        _, other_ids = _seed_minutes(theirs, ["Theirs"])
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        _member(pid, mine)
        try:
            assert _client(subject, mine).get(f"/api/minutes/{other_ids[0]}").status_code == 404
        finally:
            _cleanup([pid], [mine, theirs])

    def test_the_wire_shape_matches_the_frontend_contract(self, restore_client):
        import re
        from pathlib import Path

        source = Path("frontend/src/lib/minutes.ts").read_text()
        block = re.search(r"export type Minutes = \{(.*?)\n\};", source, re.S)
        assert block
        ts_fields = set(re.findall(r"^\s{2}(\w+)\??:", block.group(1), re.M))

        ws = _workspace("shape")
        _, ids = _seed_minutes(ws, ["Body"])
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        _member(pid, ws)
        try:
            body = _client(subject, ws).get(f"/api/minutes/{ids[0]}").json()
            assert set(body) == ts_fields, "the API response and lib/minutes.ts have drifted"
        finally:
            _cleanup([pid], [ws])
