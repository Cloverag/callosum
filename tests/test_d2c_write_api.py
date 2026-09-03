"""Resolution, commitment and board-member write endpoints (P3 CP-D — D2c).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

One file for the three remaining aggregates because they share a fixture: a decision to
hang a resolution on, and a board member to own a commitment and cast a vote.

The three rules from D1 are tested per module. What is specific here is a set of
governance properties that are easy to "improve" into being wrong, each recorded as a
decision in #58 and now pinned:

- **The vote tally does not decide the outcome.** `resolutions.tally` has no endpoint at
  all — it is a pure function computed client-side. Quorum and supermajority rules vary
  per board and nothing records them, so inferring a result would assert governance
  nobody configured.
- **Superseding a resolution does not carry its votes forward.** They were cast on the
  old text; copying them would record directors as having voted for words they never saw.
- **`blocked` is not terminal on a commitment.** Blocked work is expected to resume.
- **Deactivating a director is not a delete.** Their votes and commitments remain valid.
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
from meridian.api import auth
from meridian.api import board_members as board_members_api
from meridian.api import commitments as commitments_api
from meridian.api import errors
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
    application.include_router(commitments_api.router)
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
        "INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, 'director', 3)",
        (pid, f"API User {pid[:6]}"),
    )
    _admin(
        "INSERT INTO principal_identity (principal_id, provider, subject) VALUES (%s, %s, %s)",
        (pid, ISSUER, subject),
    )
    return pid


def _member(principal_id: str, workspace_id: str) -> None:
    # clearance 3, not the old 2: 'director' maps to 3 (#166) and this file never
    # varied clearance, so the fixture only needs to stop lying about the number,
    # not gain a role parameter no test would use.
    _admin(
        "INSERT INTO membership (principal_id, workspace_id, role, clearance, active)"
        " VALUES (%s, %s, 'director', 3, true)",
        (principal_id, workspace_id),
    )


def _cleanup(principal_ids: list[str], workspace_ids: list[str]) -> None:
    for ws in workspace_ids:
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM commitment_update WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM commitment WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM resolution_vote WHERE workspace_id = %s", (ws,))
        _admin("UPDATE resolution SET superseded_by_id = NULL WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM resolution WHERE workspace_id = %s", (ws,))
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


class _Fixture:
    """A workspace with a decision and one director, ready for anything downstream."""

    def __init__(self, label: str):
        self.subject = f"sub-{uuid.uuid4()}"
        self.pid = _principal_with_identity(self.subject)
        self.ws = _workspace(label)
        _member(self.pid, self.ws)
        m = meetings.create_meeting("Board Meeting", workspace_id=self.ws)
        self.decision = decisions.create_decision(m.id, "Adopt the plan", workspace_id=self.ws)
        self.client = _client(self.subject, self.ws)

    def director(self, name: str = "Priya Nair") -> dict:
        response = self.client.post(
            "/api/board-members", json={"full_name": name, "role": "director"}
        )
        assert response.status_code == 201, response.text
        return response.json()

    def resolution(self, title: str = "Resolution 2026-04") -> dict:
        response = self.client.post(
            "/api/resolutions",
            json={"decision_id": self.decision.id, "title": title, "body": "RESOLVED THAT …"},
        )
        assert response.status_code == 201, response.text
        return response.json()

    def commitment(self, owner: dict, title: str = "Bring the rollout plan", **kw) -> dict:
        response = self.client.post(
            "/api/commitments",
            json={
                "decision_id": self.decision.id,
                "title": title,
                "owner_board_member_id": owner["id"],
                **kw,
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    def close(self):
        _cleanup([self.pid], [self.ws])


class TestResolutions:
    def test_creates_a_draft(self, restore_client):
        f = _Fixture("res-create")
        try:
            r = f.resolution()
            assert r["status"] == "draft"
            assert r["votes"] == []
        finally:
            f.close()

    def test_a_stale_patch_is_409(self, restore_client):
        f = _Fixture("res-stale")
        try:
            r = f.resolution()
            f.client.patch(
                f"/api/resolutions/{r['id']}",
                json={"expected_version": r["version"], "title": "First"},
            )
            conflict = f.client.patch(
                f"/api/resolutions/{r['id']}",
                json={"expected_version": r["version"], "title": "Second"},
            )
            assert conflict.status_code == 409
            assert conflict.json()["error"]["code"] == "stale_resource"
        finally:
            f.close()

    def test_records_a_vote_without_a_version(self, restore_client):
        """Votes write `resolution_vote`, so two directors voting at once do not contend."""
        f = _Fixture("res-vote")
        try:
            r = f.resolution()
            d = f.director()
            response = f.client.post(
                f"/api/resolutions/{r['id']}/vote",
                json={"board_member_id": d["id"], "vote": "for"},
            )
            assert response.status_code == 201
            assert response.json()["vote"] == "for"
        finally:
            f.close()

    def test_there_is_no_tally_endpoint(self, restore_client):
        """#58 decision 2, enforced by absence.

        `tally` is a pure function with no database access, so ADR-014 gives it no
        endpoint. Exposing one would invite a client to treat the count as the outcome,
        and quorum rules vary per board with nothing recording them.
        """
        from meridian.api.main import app

        paths = app.openapi()["paths"]
        assert not any("tally" in p for p in paths), "a tally endpoint was added"

    def test_superseding_does_not_carry_votes_forward(self, restore_client):
        """They were cast on the old text.

        Copying them would record directors as having voted for words they never saw.
        """
        f = _Fixture("res-supersede")
        try:
            r = f.resolution("Original resolution")
            d = f.director()
            f.client.post(
                f"/api/resolutions/{r['id']}/vote",
                json={"board_member_id": d["id"], "vote": "for"},
            )
            current = f.client.get(f"/api/resolutions/{r['id']}").json()
            assert len(current["votes"]) == 1

            adopted = f.client.post(
                f"/api/resolutions/{r['id']}/transition",
                json={"new_status": "adopted", "expected_version": current["version"]},
            ).json()

            response = f.client.post(
                f"/api/resolutions/{r['id']}/supersede",
                json={
                    "new_title": "Amended resolution",
                    "new_body": "RESOLVED THAT, as amended …",
                    "expected_version": adopted["version"],
                },
            )
            assert response.status_code == 201
            body = response.json()
            assert body["replacement"]["votes"] == [], "votes were carried onto new text"
            assert body["superseded"]["id"] == r["id"]
            # The old resolution keeps its votes — the record of what was actually cast.
            assert len(f.client.get(f"/api/resolutions/{r['id']}").json()["votes"]) == 1
        finally:
            f.close()


class TestCommitments:
    def test_creates_against_an_active_owner(self, restore_client):
        f = _Fixture("com-create")
        try:
            c = f.commitment(f.director())
            assert c["status"] == "open"
            assert c["updates"] == []
            assert c["delivery_status"] == "not_dispatched"
        finally:
            f.close()

    def test_due_date_is_a_calendar_day(self, restore_client):
        f = _Fixture("com-date")
        try:
            c = f.commitment(f.director(), due_date="2026-09-01")
            assert c["due_date"] == "2026-09-01"
            assert "T" not in c["due_date"]
        finally:
            f.close()

    def test_omitting_a_field_leaves_it_alone(self, restore_client):
        f = _Fixture("com-omit")
        try:
            c = f.commitment(f.director(), detail="Original detail")
            patched = f.client.patch(
                f"/api/commitments/{c['id']}",
                json={"expected_version": c["version"], "title": "Renamed"},
            )
            assert patched.status_code == 200
            assert patched.json()["detail"] == "Original detail"
        finally:
            f.close()

    def test_sending_null_clears_the_due_date(self, restore_client):
        f = _Fixture("com-clear")
        try:
            c = f.commitment(f.director(), due_date="2026-09-01")
            patched = f.client.patch(
                f"/api/commitments/{c['id']}",
                json={"expected_version": c["version"], "due_date": None},
            )
            assert patched.status_code == 200
            assert patched.json()["due_date"] is None
        finally:
            f.close()

    def test_an_update_requires_a_note_even_without_a_status_change(self, restore_client):
        """A commitment's value is the trail of what happened to it."""
        f = _Fixture("com-note")
        try:
            c = f.commitment(f.director())
            response = f.client.post(
                f"/api/commitments/{c['id']}/updates",
                json={"expected_version": c["version"]},
            )
            assert response.status_code == 422
        finally:
            f.close()

    def test_blocked_is_not_terminal(self, restore_client):
        """#58 decision 3. The proposal stranded blocked work; blocked work resumes."""
        f = _Fixture("com-blocked")
        try:
            c = f.commitment(f.director())
            blocked = f.client.post(
                f"/api/commitments/{c['id']}/updates",
                json={
                    "note": "Waiting on legal",
                    "expected_version": c["version"],
                    "new_status": "blocked",
                },
            )
            assert blocked.status_code == 201
            assert blocked.json()["status"] == "blocked"

            resumed = f.client.post(
                f"/api/commitments/{c['id']}/updates",
                json={
                    "note": "Legal cleared it",
                    "expected_version": blocked.json()["version"],
                    "new_status": "in_progress",
                },
            )
            assert resumed.status_code == 201
            assert resumed.json()["status"] == "in_progress"
            assert len(resumed.json()["updates"]) == 2
        finally:
            f.close()

    def test_a_stale_update_is_409(self, restore_client):
        f = _Fixture("com-stale")
        try:
            c = f.commitment(f.director())
            f.client.post(
                f"/api/commitments/{c['id']}/updates",
                json={"note": "First", "expected_version": c["version"]},
            )
            conflict = f.client.post(
                f"/api/commitments/{c['id']}/updates",
                json={"note": "Second", "expected_version": c["version"]},
            )
            assert conflict.status_code == 409
        finally:
            f.close()

    def test_there_is_no_delivery_endpoint(self, restore_client):
        """`record_delivery_attempt` gets no route: delivery is inert until P8.

        Exposing it would be a endpoint nothing can drive — the same reasoning that
        deferred CP9 rather than shipping an empty `notification` table.
        """
        from meridian.api.main import app

        paths = app.openapi()["paths"]
        assert not any("delivery" in p for p in paths), "a delivery endpoint was added"


class TestBoardMembers:
    def test_creates_a_director(self, restore_client):
        f = _Fixture("bm-create")
        try:
            d = f.director()
            assert d["active"] is True
            assert d["voting"] == "voting"
        finally:
            f.close()

    def test_two_directors_may_share_a_name(self, restore_client):
        """No uniqueness on `(workspace_id, full_name)`, deliberately.

        Two real people can share a name, and this system's alias machinery exists
        precisely because names collide.
        """
        f = _Fixture("bm-dupe")
        try:
            first = f.director("R. Kumar")
            second = f.director("R. Kumar")
            assert first["id"] != second["id"]
        finally:
            f.close()

    def test_active_is_not_patchable(self, restore_client):
        """Leaving the board is an event, not a field edit."""
        f = _Fixture("bm-active")
        try:
            d = f.director()
            response = f.client.patch(
                f"/api/board-members/{d['id']}",
                json={"expected_version": d["version"], "active": False},
            )
            assert response.status_code == 422
        finally:
            f.close()

    def test_deactivating_is_not_deleting(self, restore_client):
        """Their votes and commitments stay valid.

        A decision taken by the board that existed at the time is not unmade by someone
        leaving, and the composite `(id, workspace_id)` FKs make removal impossible
        anyway — the constraint enforces the intent rather than describing it.
        """
        f = _Fixture("bm-deactivate")
        try:
            d = f.director()
            c = f.commitment(d)
            r = f.resolution()
            f.client.post(
                f"/api/resolutions/{r['id']}/vote",
                json={"board_member_id": d["id"], "vote": "for"},
            )

            gone = f.client.post(
                f"/api/board-members/{d['id']}/deactivate",
                json={"expected_version": d["version"]},
            )
            assert gone.status_code == 200
            assert gone.json()["active"] is False

            # Still in the directory, and everything referencing them survives.
            assert f.client.get(f"/api/board-members/{d['id']}").status_code == 200
            assert f.client.get(f"/api/commitments/{c['id']}").json()["owner_board_member_id"] == d["id"]
            assert len(f.client.get(f"/api/resolutions/{r['id']}").json()["votes"]) == 1
        finally:
            f.close()

    def test_reactivating_returns_them_to_service(self, restore_client):
        f = _Fixture("bm-reactivate")
        try:
            d = f.director()
            gone = f.client.post(
                f"/api/board-members/{d['id']}/deactivate",
                json={"expected_version": d["version"]},
            ).json()
            back = f.client.post(
                f"/api/board-members/{d['id']}/reactivate",
                json={"expected_version": gone["version"]},
            )
            assert back.status_code == 200
            assert back.json()["active"] is True
        finally:
            f.close()

    def test_a_stale_deactivate_is_409(self, restore_client):
        f = _Fixture("bm-stale")
        try:
            d = f.director()
            f.client.patch(
                f"/api/board-members/{d['id']}",
                json={"expected_version": d["version"], "organization": "Sequoia"},
            )
            conflict = f.client.post(
                f"/api/board-members/{d['id']}/deactivate",
                json={"expected_version": d["version"]},
            )
            assert conflict.status_code == 409
        finally:
            f.close()


def test_no_write_endpoint_accepts_a_workspace_id(restore_client):
    """ADR-013 across all of D2c at once, from the generated schema.

    `tests/test_openapi_input_guard.py` already walks every operation; this asserts the
    same rule specifically over the write bodies added here, so a regression names D2c
    rather than the whole app.
    """
    from meridian.api.main import app

    schema = app.openapi()
    offenders = []
    for path, ops in schema["paths"].items():
        if not any(k in path for k in ("resolution", "commitment", "board-member")):
            continue
        for method, op in ops.items():
            if method not in ("post", "patch", "put", "delete"):
                continue
            body = (op.get("requestBody") or {}).get("content", {})
            for media in body.values():
                ref = (media.get("schema") or {}).get("$ref", "")
                name = ref.rsplit("/", 1)[-1] if ref else None
                props = schema["components"]["schemas"].get(name, {}).get("properties", {}) if name else {}
                for prop in props:
                    if prop.lower().replace("_", "") in {"workspaceid", "clearance"}:
                        offenders.append(f"{method.upper()} {path}: {prop}")
    assert offenders == [], offenders
