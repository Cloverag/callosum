"""Agenda write endpoints (Meridian P3, CP-D — D2a).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

Follows the D1 pattern from `test_meetings_write_api.py`. Two things are specific to
agenda and are what these tests are really for:

- **`DELETE` carries `expected_version` as a query parameter.** A delete is a mutation
  and needs the same concurrency check; removing an item somebody just rewrote is the
  lost update the checkpoint exists to prevent.
- **`reorder` has no version at all.** It takes the complete ordered list and the
  domain rejects any set that is not exactly the meeting's items, so a stale client is
  caught by the content of the request rather than by a counter.
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

from callosum import identity
from callosum.config import settings
from meridian import meetings
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


def _member(principal_id: str, workspace_id: str, role: str = "advisor") -> None:
    """`role`, not `clearance` (#166): effective clearance is derived from
    `membership.role` at read time — a stored `clearance` this helper's caller
    picked independently is inert. No call site in this file ever passed an
    explicit value, so there was no boundary being tested by the old default
    (`clearance=2`); `role="advisor"` (2) keeps the same effective clearance
    rather than changing what any existing test exercises.
    """
    _admin(
        "INSERT INTO membership (principal_id, workspace_id, role, clearance, active)"
        " VALUES (%s, %s, %s, %s, true)",
        (principal_id, workspace_id, role, identity.ROLE_TO_CLEARANCE[role]),
    )


def _cleanup(principal_ids: list[str], workspace_ids: list[str]) -> None:
    for ws in workspace_ids:
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


class _Fixture:
    """A member, a workspace, a meeting and a signed-in client."""

    def __init__(self, label: str):
        self.subject = f"sub-{uuid.uuid4()}"
        self.pid = _principal_with_identity(self.subject)
        self.ws = _workspace(label)
        _member(self.pid, self.ws)
        self.meeting = meetings.create_meeting("Board Meeting", workspace_id=self.ws)
        self.client = _client(self.subject, self.ws)

    def add(self, title: str, **kw) -> dict:
        body = {"meeting_id": self.meeting.id, "title": title, **kw}
        response = self.client.post("/api/agenda", json=body)
        assert response.status_code == 201, response.text
        return response.json()

    def close(self):
        _cleanup([self.pid], [self.ws])


class TestCreate:
    def test_creates_and_appends_in_order(self, restore_client):
        f = _Fixture("create")
        try:
            first = f.add("Opening")
            second = f.add("Finance")
            assert first["position"] == 1
            assert second["position"] == 2
        finally:
            f.close()

    def test_a_workspace_id_in_the_body_is_refused(self, restore_client):
        f = _Fixture("forbid")
        try:
            response = f.client.post(
                "/api/agenda",
                json={"meeting_id": f.meeting.id, "title": "X", "workspace_id": f.ws},
            )
            assert response.status_code == 422
        finally:
            f.close()


class TestPatch:
    def test_omitting_a_field_leaves_it_alone(self, restore_client):
        f = _Fixture("omit")
        try:
            item = f.add("Finance", description="Q3 numbers", presenter="Priya")
            patched = f.client.patch(
                f"/api/agenda/{item['id']}",
                json={"expected_version": item["version"], "title": "Finance review"},
            )
            assert patched.status_code == 200
            assert patched.json()["title"] == "Finance review"
            assert patched.json()["description"] == "Q3 numbers"
            assert patched.json()["presenter"] == "Priya"
        finally:
            f.close()

    def test_sending_null_clears_the_field(self, restore_client):
        f = _Fixture("clear")
        try:
            item = f.add("Finance", description="Q3 numbers")
            patched = f.client.patch(
                f"/api/agenda/{item['id']}",
                json={"expected_version": item["version"], "description": None},
            )
            assert patched.status_code == 200
            assert patched.json()["description"] is None
        finally:
            f.close()

    def test_a_stale_version_is_409(self, restore_client):
        f = _Fixture("stale")
        try:
            item = f.add("Finance")
            f.client.patch(
                f"/api/agenda/{item['id']}",
                json={"expected_version": item["version"], "title": "First"},
            )
            conflict = f.client.patch(
                f"/api/agenda/{item['id']}",
                json={"expected_version": item["version"], "title": "Second"},
            )
            assert conflict.status_code == 409
            assert conflict.json()["error"]["code"] == "stale_resource"
        finally:
            f.close()

    def test_position_is_not_patchable(self, restore_client):
        """Moving an item is `reorder`, which sees the whole list."""
        f = _Fixture("nopos")
        try:
            item = f.add("Finance")
            response = f.client.patch(
                f"/api/agenda/{item['id']}",
                json={"expected_version": item["version"], "position": 5},
            )
            assert response.status_code == 422
        finally:
            f.close()


class TestDelete:
    def test_deletes_and_closes_the_position_gap(self, restore_client):
        f = _Fixture("delete")
        try:
            first = f.add("Opening")
            middle = f.add("Finance")
            last = f.add("Closing")
            response = f.client.delete(
                f"/api/agenda/{middle['id']}", params={"expected_version": middle["version"]}
            )
            assert response.status_code == 204

            remaining = f.client.get("/api/agenda", params={"meeting_id": f.meeting.id}).json()
            assert [i["id"] for i in remaining] == [first["id"], last["id"]]
            assert [i["position"] for i in remaining] == [1, 2], "a gap was left in position"
        finally:
            f.close()

    def test_expected_version_is_required(self, restore_client):
        """A delete without a version is a lost update waiting to happen."""
        f = _Fixture("needver")
        try:
            item = f.add("Finance")
            assert f.client.delete(f"/api/agenda/{item['id']}").status_code == 422
        finally:
            f.close()

    def test_a_stale_delete_is_409(self, restore_client):
        f = _Fixture("staledel")
        try:
            item = f.add("Finance")
            f.client.patch(
                f"/api/agenda/{item['id']}",
                json={"expected_version": item["version"], "title": "Edited"},
            )
            response = f.client.delete(
                f"/api/agenda/{item['id']}", params={"expected_version": item["version"]}
            )
            assert response.status_code == 409
        finally:
            f.close()


class TestReorder:
    def test_returns_the_whole_agenda_in_the_new_order(self, restore_client):
        f = _Fixture("reorder")
        try:
            a = f.add("Opening")
            b = f.add("Finance")
            c = f.add("Closing")
            response = f.client.post(
                "/api/agenda/reorder",
                json={"meeting_id": f.meeting.id, "ordered_item_ids": [c["id"], a["id"], b["id"]]},
            )
            assert response.status_code == 200
            body = response.json()
            assert [i["id"] for i in body] == [c["id"], a["id"], b["id"]]
            assert [i["position"] for i in body] == [1, 2, 3]
        finally:
            f.close()

    def test_an_incomplete_list_is_refused(self, restore_client):
        """This is what replaces `expected_version` here.

        A client working from a stale agenda sends a list missing the item somebody just
        added, and the domain refuses it — caught by the content of the request rather
        than by a counter.
        """
        f = _Fixture("partial")
        try:
            a = f.add("Opening")
            f.add("Finance")
            response = f.client.post(
                "/api/agenda/reorder",
                json={"meeting_id": f.meeting.id, "ordered_item_ids": [a["id"]]},
            )
            assert response.status_code == 422
        finally:
            f.close()
