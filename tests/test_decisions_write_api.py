"""Decision write endpoints (Meridian P3, CP-D — D2a).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

Follows the D1 pattern. Two things are specific to decisions:

- **`record_stance` has no `expected_version`** — it writes `decision_stance`, not the
  decision, and the upsert is keyed on `(decision_id, person_name)` so two directors
  voting at once do not contend. The guard that applies instead is the decision's
  *status*: stances only while `proposed`. That guard was added in review of #22, and
  the test below is what stops it being dropped.
- **`supersede` returns both halves.** The old decision is not edited away; it gains a
  `superseded_by_id` and a terminal status, which is what makes this an audit trail
  rather than a current-state table.
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
from meridian.api import auth
from meridian.api import decisions as decisions_api
from meridian.api import errors

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
    application.include_router(decisions_api.router)
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


def _cleanup(principal_ids: list[str], workspace_ids: list[str]) -> None:
    for ws in workspace_ids:
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM decision_stance WHERE workspace_id = %s", (ws,))
        _admin("UPDATE decision SET superseded_by_id = NULL WHERE workspace_id = %s", (ws,))
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


class _Fixture:
    def __init__(self, label: str):
        self.subject = f"sub-{uuid.uuid4()}"
        self.pid = _principal_with_identity(self.subject)
        self.ws = _workspace(label)
        _member(self.pid, self.ws)
        self.meeting = meetings.create_meeting("Board Meeting", workspace_id=self.ws)
        self.client = _client(self.subject, self.ws)

    def decide(self, title: str = "Adopt the FY27 plan", **kw) -> dict:
        response = self.client.post(
            "/api/decisions", json={"meeting_id": self.meeting.id, "title": title, **kw}
        )
        assert response.status_code == 201, response.text
        return response.json()

    def approve(self, decision: dict) -> dict:
        response = self.client.post(
            f"/api/decisions/{decision['id']}/transition",
            json={"new_status": "approved", "expected_version": decision["version"]},
        )
        assert response.status_code == 200, response.text
        return response.json()

    def close(self):
        _cleanup([self.pid], [self.ws])


class TestCreateAndPatch:
    def test_creates_a_proposed_decision(self, restore_client):
        f = _Fixture("create")
        try:
            body = f.decide()
            assert body["status"] == "proposed"
            assert body["version"] == 1
            assert body["stances"] == []
        finally:
            f.close()

    def test_sending_null_clears_the_rationale(self, restore_client):
        f = _Fixture("clear")
        try:
            d = f.decide(rationale="Because the board said so")
            patched = f.client.patch(
                f"/api/decisions/{d['id']}",
                json={"expected_version": d["version"], "rationale": None},
            )
            assert patched.status_code == 200
            assert patched.json()["rationale"] is None
        finally:
            f.close()

    def test_omitting_a_field_leaves_it_alone(self, restore_client):
        f = _Fixture("omit")
        try:
            d = f.decide(rationale="Kept")
            patched = f.client.patch(
                f"/api/decisions/{d['id']}",
                json={"expected_version": d["version"], "title": "Renamed"},
            )
            assert patched.json()["title"] == "Renamed"
            assert patched.json()["rationale"] == "Kept"
        finally:
            f.close()

    def test_a_stale_version_is_409(self, restore_client):
        f = _Fixture("stale")
        try:
            d = f.decide()
            f.client.patch(
                f"/api/decisions/{d['id']}",
                json={"expected_version": d["version"], "title": "First"},
            )
            conflict = f.client.patch(
                f"/api/decisions/{d['id']}",
                json={"expected_version": d["version"], "title": "Second"},
            )
            assert conflict.status_code == 409
            assert conflict.json()["error"]["code"] == "stale_resource"
        finally:
            f.close()

    def test_a_workspace_id_in_the_body_is_refused(self, restore_client):
        f = _Fixture("forbid")
        try:
            response = f.client.post(
                "/api/decisions",
                json={"meeting_id": f.meeting.id, "title": "X", "workspace_id": f.ws},
            )
            assert response.status_code == 422
        finally:
            f.close()


class TestStance:
    def test_records_a_stance(self, restore_client):
        f = _Fixture("stance")
        try:
            d = f.decide()
            response = f.client.post(
                f"/api/decisions/{d['id']}/stance",
                json={"person_name": "Priya Nair", "stance": "SUPPORTED"},
            )
            assert response.status_code == 201
            assert response.json()["person_name"] == "Priya Nair"
            assert response.json()["stance"] == "SUPPORTED"
            assert response.json()["board_member_id"] is None
        finally:
            f.close()

    def test_a_second_stance_from_the_same_person_replaces_the_first(self, restore_client):
        """Upsert on `(decision_id, person_name)` — changing your mind is not a new vote."""
        f = _Fixture("upsert")
        try:
            d = f.decide()
            for stance in ("SUPPORTED", "OPPOSED"):
                f.client.post(
                    f"/api/decisions/{d['id']}/stance",
                    json={"person_name": "Priya Nair", "stance": stance},
                )
            stances = f.client.get(f"/api/decisions/{d['id']}").json()["stances"]
            assert len(stances) == 1
            assert stances[0]["stance"] == "OPPOSED"
        finally:
            f.close()

    def test_a_stance_on_an_approved_decision_is_409(self, restore_client):
        """The guard added in review of #22.

        Without it, votes could be added to an already-approved decision, contradicting
        the immutability the approval is supposed to establish.
        """
        f = _Fixture("locked")
        try:
            d = f.approve(f.decide())
            response = f.client.post(
                f"/api/decisions/{d['id']}/stance",
                json={"person_name": "Late Voter", "stance": "OPPOSED"},
            )
            assert response.status_code == 409
        finally:
            f.close()


class TestTransitionAndSupersede:
    def test_an_illegal_move_is_409(self, restore_client):
        """#97, now fixed: the same as `meetings`, `resolutions` and `commitments`.

        The request was well-formed and the state refused it. There is no input to
        correct, so a 422 would tell the caller to fix nothing and resend forever.
        """
        f = _Fixture("illegal")
        try:
            d = f.approve(f.decide())
            response = f.client.post(
                f"/api/decisions/{d['id']}/transition",
                json={"new_status": "proposed", "expected_version": d["version"]},
            )
            assert response.status_code == 409
        finally:
            f.close()

    def test_deferred_is_terminal(self, restore_client):
        """A recorded product decision, not an oversight — see the review of #22."""
        f = _Fixture("deferred")
        try:
            d = f.decide()
            deferred = f.client.post(
                f"/api/decisions/{d['id']}/transition",
                json={"new_status": "deferred", "expected_version": d["version"]},
            ).json()
            response = f.client.post(
                f"/api/decisions/{deferred['id']}/transition",
                json={"new_status": "approved", "expected_version": deferred["version"]},
            )
            # 409 for the same reason as above, not because `deferred` is special.
            assert response.status_code == 409
        finally:
            f.close()

    def test_supersede_returns_both_halves_and_keeps_the_original(self, restore_client):
        f = _Fixture("supersede")
        try:
            approved = f.approve(f.decide("Original decision"))
            response = f.client.post(
                f"/api/decisions/{approved['id']}/supersede",
                json={"new_title": "Revised decision", "expected_version": approved["version"]},
            )
            assert response.status_code == 201
            body = response.json()

            assert body["replacement"]["title"] == "Revised decision"
            assert body["replacement"]["status"] == "proposed"
            assert body["superseded"]["id"] == approved["id"]
            assert body["superseded"]["status"] == "superseded"
            assert body["superseded"]["superseded_by_id"] == body["replacement"]["id"]

            # The original is still readable. Supersession is a trail, not a deletion.
            still_there = f.client.get(f"/api/decisions/{approved['id']}")
            assert still_there.status_code == 200
            assert still_there.json()["title"] == "Original decision"
        finally:
            f.close()

    def test_only_an_approved_decision_may_be_superseded(self, restore_client):
        f = _Fixture("notapproved")
        try:
            d = f.decide()
            response = f.client.post(
                f"/api/decisions/{d['id']}/supersede",
                json={"new_title": "Too early", "expected_version": d["version"]},
            )
            assert response.status_code in (409, 422)
        finally:
            f.close()
