"""Minutes write endpoints (Meridian P3, CP-D — D2b).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

**No clearance anywhere, and that is the contract rather than an omission.** The
`minutes` table has no `sensitivity` column and no domain function accepts a clearance
— minutes are workspace-scoped only. Whether they *should* be filtered is a live
question (#49, resolved as ADR-015: workspace-scoped by design). These endpoints mirror
the contract exactly rather than inventing a filter the domain cannot honour.

The property worth protecting here is different from packs. Minutes are the record of
what a board was told, so the value is that a finalised version stays readable forever:
a correction is a new version, never an edit.
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


def _member(principal_id: str, workspace_id: str) -> None:
    _admin(
        "INSERT INTO membership (principal_id, workspace_id, role, clearance, active)"
        " VALUES (%s, %s, 'director', 2, true)",
        (principal_id, workspace_id),
    )


def _cleanup(principal_ids: list[str], workspace_ids: list[str]) -> None:
    for ws in workspace_ids:
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


class _Fixture:
    """A meeting that has actually happened — minutes are refused before that."""

    def __init__(self, label: str, status: str = "in_progress"):
        self.subject = f"sub-{uuid.uuid4()}"
        self.pid = _principal_with_identity(self.subject)
        self.ws = _workspace(label)
        _member(self.pid, self.ws)
        m = meetings.create_meeting(
            "Board Meeting",
            workspace_id=self.ws,
            scheduled_start="2026-09-01T10:00:00+00:00",
            scheduled_end="2026-09-01T11:00:00+00:00",
        )
        if status != "draft":
            m = meetings.transition_status(m.id, "scheduled", expected_version=m.version, workspace_id=self.ws)
            if status in ("in_progress", "completed"):
                m = meetings.transition_status(
                    m.id, "in_progress", expected_version=m.version, workspace_id=self.ws
                )
            if status == "completed":
                m = meetings.transition_status(
                    m.id, "completed", expected_version=m.version, workspace_id=self.ws
                )
        self.meeting = m
        self.client = _client(self.subject, self.ws)

    def minutes(self, body: str = "The board met and resolved as follows.") -> dict:
        response = self.client.post(
            "/api/minutes", json={"meeting_id": self.meeting.id, "body": body}
        )
        assert response.status_code == 201, response.text
        return response.json()

    def close(self):
        _cleanup([self.pid], [self.ws])


class TestCreateAndEdit:
    def test_creates_draft_minutes(self, restore_client):
        f = _Fixture("create")
        try:
            body = f.minutes()
            assert body["status"] == "draft"
            assert body["version"] == 1
        finally:
            f.close()

    def test_minutes_are_refused_before_a_meeting_happens(self, restore_client):
        """There is nothing to minute about a meeting that has not started."""
        f = _Fixture("early", status="draft")
        try:
            response = f.client.post(
                "/api/minutes", json={"meeting_id": f.meeting.id, "body": "Premature"}
            )
            assert response.status_code == 409
        finally:
            f.close()

    def test_a_null_body_is_refused(self, restore_client):
        """`NOT NULL` in the schema, refused at the boundary rather than in the domain."""
        f = _Fixture("nullbody")
        try:
            m = f.minutes()
            response = f.client.patch(
                f"/api/minutes/{m['id']}", json={"expected_version": m["version"], "body": None}
            )
            assert response.status_code == 422
        finally:
            f.close()

    def test_a_stale_patch_is_409(self, restore_client):
        f = _Fixture("stale")
        try:
            m = f.minutes()
            f.client.patch(
                f"/api/minutes/{m['id']}",
                json={"expected_version": m["version"], "body": "First revision"},
            )
            conflict = f.client.patch(
                f"/api/minutes/{m['id']}",
                json={"expected_version": m["version"], "body": "Second revision"},
            )
            assert conflict.status_code == 409
            assert conflict.json()["error"]["code"] == "stale_resource"
        finally:
            f.close()

    def test_a_workspace_id_in_the_body_is_refused(self, restore_client):
        f = _Fixture("forbid")
        try:
            response = f.client.post(
                "/api/minutes",
                json={"meeting_id": f.meeting.id, "body": "X", "workspace_id": f.ws},
            )
            assert response.status_code == 422
        finally:
            f.close()


class TestFinaliseIsIrreversible:
    """The property that makes minutes worth having."""

    def test_finalised_minutes_refuse_edits(self, restore_client):
        f = _Fixture("final")
        try:
            m = f.minutes()
            finalised = f.client.post(
                f"/api/minutes/{m['id']}/finalise", json={"expected_version": m["version"]}
            )
            assert finalised.status_code == 200
            assert finalised.json()["status"] == "final"

            refused = f.client.patch(
                f"/api/minutes/{m['id']}",
                json={"expected_version": finalised.json()["version"], "body": "Quietly reworded"},
            )
            assert refused.status_code == 409
        finally:
            f.close()

    def test_a_correction_is_a_new_version_and_the_old_one_survives(self, restore_client):
        """What the board was told at the time stays recoverable."""
        f = _Fixture("correct")
        try:
            m = f.minutes("Original record of the meeting.")
            finalised = f.client.post(
                f"/api/minutes/{m['id']}/finalise", json={"expected_version": m["version"]}
            ).json()

            response = f.client.post(
                f"/api/minutes/{m['id']}/supersede",
                json={
                    "new_body": "Corrected record of the meeting.",
                    "expected_version": finalised["version"],
                },
            )
            assert response.status_code == 201
            body = response.json()

            assert body["replacement"]["body"] == "Corrected record of the meeting."
            assert body["superseded"]["id"] == m["id"]
            assert body["superseded"]["superseded_by_id"] == body["replacement"]["id"]

            original = f.client.get(f"/api/minutes/{m['id']}")
            assert original.status_code == 200
            assert original.json()["body"] == "Original record of the meeting."
        finally:
            f.close()

    def test_draft_minutes_cannot_be_superseded(self, restore_client):
        """Supersession is for correcting a record, and a draft is not one yet."""
        f = _Fixture("draftsupersede")
        try:
            m = f.minutes()
            response = f.client.post(
                f"/api/minutes/{m['id']}/supersede",
                json={"new_body": "Too early", "expected_version": m["version"]},
            )
            assert response.status_code in (409, 422)
        finally:
            f.close()
