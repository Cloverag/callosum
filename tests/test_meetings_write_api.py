"""Meeting write endpoints (Meridian P3, CP-D — writes and concurrency).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

D1 — the first aggregate, so these tests establish what every other module's writes
have to prove:

1. **`created_by` cannot be supplied by the client.** An authorship claim the request
   can choose is not an authorship claim.
2. **A version mismatch is 409, not 422.** The request was well-formed; the *state*
   refused it. Same for an illegal transition.
3. **PATCH keeps absent, null and value distinct.** Omit to leave alone, `null` to
   clear, value to set. The domain already models this with `_UNSET`; these tests are
   what stop the endpoint collapsing it.

The concurrency test is the one that matters: two writers read the same version and
the second one loses. That is the behaviour the whole checkpoint exists for, and it is
asserted end to end over HTTP rather than against the domain function.
"""

import datetime as dt
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


def _cleanup(principal_ids: list[str], workspace_ids: list[str]) -> None:
    for ws in workspace_ids:
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


class TestCreate:
    def test_creates_a_draft_and_returns_201(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("create")
        _member(pid, ws)
        try:
            response = _client(subject, ws).post("/api/meetings", json={"title": "Board Meeting 17"})
            assert response.status_code == 201
            body = response.json()
            assert body["title"] == "Board Meeting 17"
            assert body["status"] == "draft"
            assert body["version"] == 1
        finally:
            _cleanup([pid], [ws])

    def test_created_by_is_the_session_principal(self, restore_client):
        """Not the client's to choose. There is nowhere in the request to say otherwise."""
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("author")
        _member(pid, ws)
        try:
            body = _client(subject, ws).post("/api/meetings", json={"title": "Authored"}).json()
            assert body["created_by"] == pid
        finally:
            _cleanup([pid], [ws])

    def test_a_forged_created_by_is_refused_not_ignored(self, restore_client):
        """`extra="forbid"`, so the attempt fails loudly.

        Silently dropping it would be safe but teach a client that the field works.
        """
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        other = _principal_with_identity(f"other-{uuid.uuid4()}")
        ws = _workspace("forge")
        _member(pid, ws)
        try:
            response = _client(subject, ws).post(
                "/api/meetings", json={"title": "Forged", "created_by": other}
            )
            assert response.status_code == 422
        finally:
            _cleanup([pid, other], [ws])

    def test_a_workspace_id_in_the_body_is_refused(self, restore_client):
        """ADR-013 over HTTP. The OpenAPI guard proves it is not *declared*; this proves
        that sending it anyway does not work.
        """
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        mine = _workspace("mine")
        theirs = _workspace("theirs")
        _member(pid, mine)
        try:
            response = _client(subject, mine).post(
                "/api/meetings", json={"title": "Elsewhere", "workspace_id": theirs}
            )
            assert response.status_code == 422
        finally:
            _cleanup([pid], [mine, theirs])

    def test_an_end_before_its_start_is_422(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("window")
        _member(pid, ws)
        try:
            response = _client(subject, ws).post(
                "/api/meetings",
                json={
                    "title": "Backwards",
                    "scheduled_start": "2026-09-01T10:00:00Z",
                    "scheduled_end": "2026-09-01T09:00:00Z",
                },
            )
            assert response.status_code == 422
        finally:
            _cleanup([pid], [ws])


class TestPatchTriState:
    """Absent, null and value are three different instructions."""

    def test_omitting_a_field_leaves_it_alone(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("omit")
        _member(pid, ws)
        client = None
        try:
            client = _client(subject, ws)
            created = client.post(
                "/api/meetings", json={"title": "Original", "location": "Room A"}
            ).json()
            patched = client.patch(
                f"/api/meetings/{created['id']}",
                json={"expected_version": created["version"], "title": "Renamed"},
            )
            assert patched.status_code == 200
            assert patched.json()["title"] == "Renamed"
            assert patched.json()["location"] == "Room A", "an omitted field was overwritten"
        finally:
            _cleanup([pid], [ws])

    def test_sending_null_clears_the_field(self, restore_client):
        """The behaviour that a `None`-means-no-change shortcut would make impossible."""
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("clear")
        _member(pid, ws)
        try:
            client = _client(subject, ws)
            created = client.post(
                "/api/meetings", json={"title": "Has a room", "location": "Room A"}
            ).json()
            patched = client.patch(
                f"/api/meetings/{created['id']}",
                json={"expected_version": created["version"], "location": None},
            )
            assert patched.status_code == 200
            assert patched.json()["location"] is None
        finally:
            _cleanup([pid], [ws])

    def test_a_null_title_is_refused(self, restore_client):
        """`NOT NULL` in the schema, so it is refused here rather than in the domain."""
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("nulltitle")
        _member(pid, ws)
        try:
            client = _client(subject, ws)
            created = client.post("/api/meetings", json={"title": "Named"}).json()
            response = client.patch(
                f"/api/meetings/{created['id']}",
                json={"expected_version": created["version"], "title": None},
            )
            assert response.status_code == 422
        finally:
            _cleanup([pid], [ws])

    def test_an_empty_patch_is_422(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("empty")
        _member(pid, ws)
        try:
            client = _client(subject, ws)
            created = client.post("/api/meetings", json={"title": "Nothing to do"}).json()
            response = client.patch(
                f"/api/meetings/{created['id']}", json={"expected_version": created["version"]}
            )
            assert response.status_code == 422
        finally:
            _cleanup([pid], [ws])


class TestConcurrency:
    """The reason CP-D exists."""

    def test_the_second_writer_of_two_gets_409(self, restore_client):
        """Both read version 1. The first write wins; the second is told, not silently
        applied over the top.
        """
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("race")
        _member(pid, ws)
        try:
            client = _client(subject, ws)
            created = client.post("/api/meetings", json={"title": "Contended"}).json()
            stale_version = created["version"]

            first = client.patch(
                f"/api/meetings/{created['id']}",
                json={"expected_version": stale_version, "title": "Winner"},
            )
            assert first.status_code == 200
            assert first.json()["version"] == stale_version + 1

            second = client.patch(
                f"/api/meetings/{created['id']}",
                json={"expected_version": stale_version, "title": "Loser"},
            )
            assert second.status_code == 409

            # And the losing write did not land.
            assert client.get(f"/api/meetings/{created['id']}").json()["title"] == "Winner"
        finally:
            _cleanup([pid], [ws])

    def test_the_409_names_the_conflict_so_a_client_can_act_on_it(self, restore_client):
        """D3 needs this: a 409 must be actionable, not a toast saying "error"."""
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("code")
        _member(pid, ws)
        try:
            client = _client(subject, ws)
            created = client.post("/api/meetings", json={"title": "Coded"}).json()
            client.patch(
                f"/api/meetings/{created['id']}",
                json={"expected_version": created["version"], "title": "First"},
            )
            conflict = client.patch(
                f"/api/meetings/{created['id']}",
                json={"expected_version": created["version"], "title": "Second"},
            )
            assert conflict.status_code == 409
            assert conflict.json()["error"]["code"] == "stale_resource"
        finally:
            _cleanup([pid], [ws])

    def test_a_meeting_in_another_workspace_is_404_not_409(self, restore_client):
        """RLS means the row is not there, so it is missing rather than contended.

        Answering 409 would confirm the meeting exists to someone who cannot read it.
        """
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        mine = _workspace("mine")
        theirs = _workspace("theirs")
        _member(pid, mine)
        try:
            from meridian import meetings as domain

            created = domain.create_meeting("Not yours", workspace_id=theirs)
            response = _client(subject, mine).patch(
                f"/api/meetings/{created.id}",
                json={"expected_version": created.version, "title": "Reaching"},
            )
            assert response.status_code == 404
        finally:
            _cleanup([pid], [mine, theirs])


class TestTransition:
    def test_moves_through_the_state_machine(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("transition")
        _member(pid, ws)
        try:
            client = _client(subject, ws)
            created = client.post(
                "/api/meetings",
                json={
                    "title": "Movable",
                    "scheduled_start": "2026-09-01T10:00:00Z",
                    "scheduled_end": "2026-09-01T11:00:00Z",
                },
            ).json()
            response = client.post(
                f"/api/meetings/{created['id']}/transition",
                json={"new_status": "scheduled", "expected_version": created["version"]},
            )
            assert response.status_code == 200
            assert response.json()["status"] == "scheduled"
        finally:
            _cleanup([pid], [ws])

    def test_scheduling_without_a_window_is_422_not_409(self, restore_client):
        """The distinction the whole taxonomy rests on.

        `draft -> scheduled` is a *legal* move, so this is not the state machine
        refusing. It is an invariant of the target state going unmet — the caller has
        to supply something, which is 422. A 409 would tell them to retry, and retrying
        would fail forever.
        """
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("nowindow")
        _member(pid, ws)
        try:
            client = _client(subject, ws)
            created = client.post("/api/meetings", json={"title": "Undated"}).json()
            response = client.post(
                f"/api/meetings/{created['id']}/transition",
                json={"new_status": "scheduled", "expected_version": created["version"]},
            )
            assert response.status_code == 422
        finally:
            _cleanup([pid], [ws])

    def test_an_illegal_move_is_409_not_422(self, restore_client):
        """The request was well-formed; the state refused it. `draft` cannot go straight
        to `completed`.
        """
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("illegal")
        _member(pid, ws)
        try:
            client = _client(subject, ws)
            created = client.post("/api/meetings", json={"title": "Impatient"}).json()
            response = client.post(
                f"/api/meetings/{created['id']}/transition",
                json={"new_status": "completed", "expected_version": created["version"]},
            )
            assert response.status_code == 409
        finally:
            _cleanup([pid], [ws])

    def test_a_stale_version_on_transition_is_409(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("stalemove")
        _member(pid, ws)
        try:
            client = _client(subject, ws)
            created = client.post("/api/meetings", json={"title": "Raced"}).json()
            client.patch(
                f"/api/meetings/{created['id']}",
                json={"expected_version": created["version"], "title": "Bumped"},
            )
            response = client.post(
                f"/api/meetings/{created['id']}/transition",
                json={"new_status": "scheduled", "expected_version": created["version"]},
            )
            assert response.status_code == 409
        finally:
            _cleanup([pid], [ws])

    def test_status_is_not_patchable(self, restore_client):
        """One way to change status, and it is the one that enforces the machine."""
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("nopatch")
        _member(pid, ws)
        try:
            client = _client(subject, ws)
            created = client.post("/api/meetings", json={"title": "Fixed"}).json()
            response = client.patch(
                f"/api/meetings/{created['id']}",
                json={"expected_version": created["version"], "status": "completed"},
            )
            assert response.status_code == 422
        finally:
            _cleanup([pid], [ws])


def test_the_creation_timestamp_survives_a_patch(restore_client):
    """`updated_at` moves, `created_at` does not — audit data, not a cache."""
    subject = f"sub-{uuid.uuid4()}"
    pid = _principal_with_identity(subject)
    ws = _workspace("timestamps")
    _member(pid, ws)
    try:
        client = _client(subject, ws)
        created = client.post("/api/meetings", json={"title": "Timed"}).json()
        patched = client.patch(
            f"/api/meetings/{created['id']}",
            json={"expected_version": created["version"], "title": "Retimed"},
        ).json()
        assert patched["created_at"] == created["created_at"]
        assert dt.datetime.fromisoformat(patched["updated_at"]) >= dt.datetime.fromisoformat(
            created["updated_at"]
        )
    finally:
        _cleanup([pid], [ws])
