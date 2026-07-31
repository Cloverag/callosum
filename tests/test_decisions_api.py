"""The decisions read endpoints (Meridian P3, CP-C — ADR-014).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

Same shape as `test_resolutions_api.py`, with two things specific to this module:

1. `list_decisions` requires `meeting_id`, so there is a test that omitting it is a 422
   rather than an unscoped listing.
2. `DecisionStance.board_member_id` was declared in `frontend/src/lib/decisions.ts` and
   absent from the Python dataclass — the sixth contract defect found by a mock swap,
   and the first found *before* the swap rather than during it. The wire-shape test
   below is what would have caught it.
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
from meridian import decisions, meetings
from meridian.api import auth, errors
from meridian.api import decisions as decisions_api

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


def _seed_decision(workspace_id: str, title: str = "A decision") -> tuple[str, str]:
    """Returns `(meeting_id, decision_id)`."""
    m = meetings.create_meeting("Board Meeting", workspace_id=workspace_id)
    d = decisions.create_decision(m.id, title, workspace_id=workspace_id)
    return m.id, d.id


def _board_member(workspace_id: str, full_name: str = "Priya Nair") -> str:
    bid = str(uuid.uuid4())
    _admin(
        "INSERT INTO board_member (id, workspace_id, full_name, role) VALUES (%s, %s, %s, 'director')",
        (bid, workspace_id, full_name),
    )
    return bid


def _cleanup(principal_ids: list[str], workspace_ids: list[str]) -> None:
    for ws in workspace_ids:
        # `record_stance` emits an audit event (CP8), which references the workspace.
        # Dropping the workspace without clearing these is an FK violation — the tests
        # that record a stance are the only ones that hit it.
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM decision_stance WHERE workspace_id = %s", (ws,))
        _admin("UPDATE decision SET superseded_by_id = NULL WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM decision WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM board_member WHERE workspace_id = %s", (ws,))
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
    def test_lists_decisions_for_a_meeting(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("list")
        _member(pid, ws)
        mid, did = _seed_decision(ws, "Adopt the FY27 plan")
        try:
            response = _client(subject, ws).get("/api/decisions", params={"meeting_id": mid})
            assert response.status_code == 200
            body = response.json()
            assert [d["id"] for d in body] == [did]
            assert body[0]["title"] == "Adopt the FY27 plan"
        finally:
            _cleanup([pid], [ws])

    def test_meeting_id_is_required(self, restore_client):
        """The shape difference from every other read module.

        A decision exists only in the context of a meeting, so there is no
        workspace-wide listing to fall back to. Omitting the parameter must fail
        loudly rather than quietly widen the query.
        """
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("required")
        _member(pid, ws)
        try:
            assert _client(subject, ws).get("/api/decisions").status_code == 422
        finally:
            _cleanup([pid], [ws])

    def test_fetches_one_decision_with_its_stances(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("get")
        _member(pid, ws)
        _, did = _seed_decision(ws)
        try:
            response = _client(subject, ws).get(f"/api/decisions/{did}")
            assert response.status_code == 200
            assert response.json()["id"] == did
            assert response.json()["stances"] == []
        finally:
            _cleanup([pid], [ws])

    def test_a_decision_in_another_workspace_is_404(self, restore_client):
        """Not because the route checks, but because RLS means the row is not there."""
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        mine = _workspace("mine")
        theirs = _workspace("theirs")
        _member(pid, mine)
        _, did = _seed_decision(theirs)
        try:
            assert _client(subject, mine).get(f"/api/decisions/{did}").status_code == 404
        finally:
            _cleanup([pid], [mine, theirs])

    def test_an_unknown_status_is_422_without_the_route_saying_so(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("status")
        _member(pid, ws)
        mid, _ = _seed_decision(ws)
        try:
            response = _client(subject, ws).get(
                "/api/decisions", params={"meeting_id": mid, "status": "ratified"}
            )
            assert response.status_code == 422
        finally:
            _cleanup([pid], [ws])


class TestTheWireShapeMatchesTheFrontendContract:
    """Cross-language drift check — the sixth defect, and the first caught early.

    `frontend/src/lib/decisions.ts` declared `board_member_id` on `DecisionStance`,
    documented at length, including which migration added the column. The Python
    dataclass had no such field, and `_row_to_stance` dropped it — so every stance
    resolved to a director would have arrived at the browser looking unresolved.

    `SELECT *` had been fetching the column the whole time. Nothing surfaced it.
    """

    @staticmethod
    def _ts_fields(type_name: str) -> set[str]:
        import re
        from pathlib import Path

        source = Path("frontend/src/lib/decisions.ts").read_text()
        block = re.search(rf"export type {type_name} = \{{(.*?)\n\}};", source, re.S)
        assert block, f"{type_name} not found in decisions.ts"
        return set(re.findall(r"^\s{2}(\w+)\??:", block.group(1), re.M))

    def test_the_response_carries_exactly_the_declared_fields(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("shape")
        _member(pid, ws)
        _, did = _seed_decision(ws)
        try:
            body = _client(subject, ws).get(f"/api/decisions/{did}").json()
            assert set(body) == self._ts_fields("Decision"), (
                "the API response and lib/decisions.ts have drifted"
            )
        finally:
            _cleanup([pid], [ws])

    def test_the_stance_shape_matches_too(self, restore_client):
        import dataclasses

        from meridian.decisions import DecisionStance

        python_fields = {f.name for f in dataclasses.fields(DecisionStance)}
        assert python_fields == self._ts_fields("DecisionStance")

    def test_a_resolved_stance_carries_its_board_member_id(self, restore_client):
        """The regression test for the defect itself.

        Seeded through admin SQL because `record_stance()` has no `board_member_id`
        argument — resolving a minuted name to the directory is a write concern and
        CP-C is reads. This asserts only that the read path stops discarding it.
        """
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("resolved")
        _member(pid, ws)
        _, did = _seed_decision(ws)
        bid = _board_member(ws)
        try:
            decisions.record_stance(did, "Priya Nair", "SUPPORTED", workspace_id=ws)
            _admin(
                "UPDATE decision_stance SET board_member_id = %s WHERE decision_id = %s",
                (bid, did),
            )
            body = _client(subject, ws).get(f"/api/decisions/{did}").json()
            assert body["stances"][0]["board_member_id"] == bid
        finally:
            _cleanup([pid], [ws])

    def test_an_unresolved_stance_is_null_not_missing(self, restore_client):
        """`null` means "not resolved to the directory" and is a valid, permanent state.

        A stance recorded before the directory existed, or against someone who is not in
        it, is still a valid stance. The key must be present and null, never absent.
        """
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("unresolved")
        _member(pid, ws)
        _, did = _seed_decision(ws)
        try:
            decisions.record_stance(did, "Someone Not In The Directory", "OPPOSED", workspace_id=ws)
            body = _client(subject, ws).get(f"/api/decisions/{did}").json()
            stance = body["stances"][0]
            assert "board_member_id" in stance
            assert stance["board_member_id"] is None
        finally:
            _cleanup([pid], [ws])

    def test_timestamps_serialise_as_iso_strings(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("iso")
        _member(pid, ws)
        _, did = _seed_decision(ws)
        try:
            body = _client(subject, ws).get(f"/api/decisions/{did}").json()
            assert isinstance(body["created_at"], str)
            assert body["created_at"][4] == "-" and "T" in body["created_at"]
            assert body["superseded_by_id"] is None  # a proposed decision has none
        finally:
            _cleanup([pid], [ws])
