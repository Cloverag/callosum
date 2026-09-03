"""The commitments read endpoints (Meridian P3, CP-C — ADR-014).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

The last CP-C module, and **the first mock swap that found no contract defect.**
`lib/commitments.ts` matches `meridian/commitments.py` field for field, status for
status, transition for transition, and sort clause for sort clause.

That is not luck. Every earlier defect came from a mock written *before* its domain
existed — `include_inactive` invented, three phantom `Meeting` fields, `board_member_id`
declared against nothing. `commitments.ts` was written after CP7 shipped, against the
real contract. The tests below still pin it, because "matches today" and "cannot drift
tomorrow" are different properties.
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

from callosum import identity
from callosum.config import settings
from meridian import commitments, decisions, meetings
from meridian.api import auth, errors
from meridian.api import commitments as commitments_api

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
    application.include_router(commitments_api.router)
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


def _board_member(workspace_id: str, full_name: str = "Priya Nair") -> str:
    bid = str(uuid.uuid4())
    _admin(
        "INSERT INTO board_member (id, workspace_id, full_name, role) VALUES (%s, %s, %s, 'director')",
        (bid, workspace_id, full_name),
    )
    return bid


def _seed_commitment(
    workspace_id: str,
    owner: str,
    title: str = "Bring the revised rollout plan",
    due_date: dt.date | None = None,
) -> str:
    m = meetings.create_meeting("Board Meeting", workspace_id=workspace_id)
    d = decisions.create_decision(m.id, "A decision", workspace_id=workspace_id)
    c = commitments.create_commitment(
        d.id, title, owner, workspace_id=workspace_id, due_date=due_date
    )
    return c.id


def _cleanup(principal_ids: list[str], workspace_ids: list[str]) -> None:
    for ws in workspace_ids:
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM commitment_update WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM commitment WHERE workspace_id = %s", (ws,))
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
    def test_lists_commitments_in_the_session_workspace(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("list")
        _member(pid, ws)
        owner = _board_member(ws)
        cid = _seed_commitment(ws, owner, "Reconcile the customer credits")
        try:
            response = _client(subject, ws).get("/api/commitments")
            assert response.status_code == 200
            body = response.json()
            assert [c["id"] for c in body] == [cid]
            assert body[0]["title"] == "Reconcile the customer credits"
        finally:
            _cleanup([pid], [ws])

    def test_fetches_one_commitment_with_its_update_trail(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("get")
        _member(pid, ws)
        owner = _board_member(ws)
        cid = _seed_commitment(ws, owner)
        try:
            response = _client(subject, ws).get(f"/api/commitments/{cid}")
            assert response.status_code == 200
            assert response.json()["id"] == cid
            assert response.json()["updates"] == []
        finally:
            _cleanup([pid], [ws])

    def test_a_commitment_in_another_workspace_is_404(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        mine = _workspace("mine")
        theirs = _workspace("theirs")
        _member(pid, mine)
        cid = _seed_commitment(theirs, _board_member(theirs))
        try:
            assert _client(subject, mine).get(f"/api/commitments/{cid}").status_code == 404
        finally:
            _cleanup([pid], [mine, theirs])

    def test_an_unknown_status_is_422_without_the_route_saying_so(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("status")
        _member(pid, ws)
        try:
            response = _client(subject, ws).get("/api/commitments", params={"status": "done"})
            assert response.status_code == 422
        finally:
            _cleanup([pid], [ws])

    def test_open_only_excludes_closed_work(self, restore_client):
        """The filter that exists because no single status answers the board's question."""
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("open")
        _member(pid, ws)
        owner = _board_member(ws)
        still_open = _seed_commitment(ws, owner, "Still running")
        closed = _seed_commitment(ws, owner, "Finished")
        try:
            commitments.record_update(
                closed, "Shipped", expected_version=1, new_status="in_progress", workspace_id=ws
            )
            commitments.record_update(
                closed, "Done", expected_version=2, new_status="completed", workspace_id=ws
            )
            body = _client(subject, ws).get("/api/commitments", params={"open_only": True}).json()
            ids = [c["id"] for c in body]
            assert still_open in ids
            assert closed not in ids
        finally:
            _cleanup([pid], [ws])


class TestTheWireShapeMatchesTheFrontendContract:
    """Cross-language drift check.

    The first module where this found nothing. It stays because matching today and
    being unable to drift tomorrow are different properties, and five of the six
    defects so far were introduced by an edit to one side long after both were written.
    """

    @staticmethod
    def _ts_fields(type_name: str) -> set[str]:
        import re
        from pathlib import Path

        source = Path("frontend/src/lib/commitments.ts").read_text()
        block = re.search(rf"export type {type_name} = \{{(.*?)\n\}};", source, re.S)
        assert block, f"{type_name} not found in commitments.ts"
        return set(re.findall(r"^\s{2}(\w+)\??:", block.group(1), re.M))

    @staticmethod
    def _ts_union(type_name: str) -> set[str]:
        import re
        from pathlib import Path

        source = Path("frontend/src/lib/commitments.ts").read_text()
        block = re.search(rf"export type {type_name} =(.*?);", source, re.S)
        assert block, f"{type_name} not found in commitments.ts"
        return set(re.findall(r'"(\w+)"', block.group(1)))

    def test_the_response_carries_exactly_the_declared_fields(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("shape")
        _member(pid, ws)
        cid = _seed_commitment(ws, _board_member(ws))
        try:
            body = _client(subject, ws).get(f"/api/commitments/{cid}").json()
            assert set(body) == self._ts_fields("Commitment"), (
                "the API response and lib/commitments.ts have drifted"
            )
        finally:
            _cleanup([pid], [ws])

    def test_the_update_shape_matches_too(self, restore_client):
        import dataclasses

        from meridian.commitments import CommitmentUpdate

        python_fields = {f.name for f in dataclasses.fields(CommitmentUpdate)}
        assert python_fields == self._ts_fields("CommitmentUpdate")

    def test_the_statuses_are_exactly_the_domain_statuses(self, restore_client):
        assert self._ts_union("CommitmentStatus") == set(commitments.COMMITMENT_STATUSES)

    def test_the_delivery_statuses_match(self, restore_client):
        assert self._ts_union("DeliveryStatus") == set(commitments.DELIVERY_STATUSES)

    def test_blocked_is_not_terminal_on_either_side(self, restore_client):
        """Pins decision 3 from the CP7 handoff (#58).

        The proposal had `open → in_progress → {completed, blocked, cancelled}`, which
        strands blocked work. Blocked work is expected to resume. If either side ever
        makes it an exit, this fails.
        """
        assert commitments._ALLOWED_TRANSITIONS[commitments.BLOCKED]
        import re
        from pathlib import Path

        source = Path("frontend/src/lib/commitments.ts").read_text()
        block = re.search(r"blocked: \[(.*?)\],", source)
        assert block and block.group(1).strip(), "lib/commitments.ts made `blocked` terminal"

    def test_undated_work_sorts_after_dated_work(self, restore_client):
        """`ORDER BY due_date ASC NULLS LAST` — a commitment with no deadline is not
        the most urgent thing on the list. `lib/commitments.ts` sorts the same way.
        """
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("sort")
        _member(pid, ws)
        owner = _board_member(ws)
        undated = _seed_commitment(ws, owner, "No deadline")
        dated = _seed_commitment(ws, owner, "Due soon", due_date=dt.date(2026, 9, 1))
        try:
            body = _client(subject, ws).get("/api/commitments").json()
            ids = [c["id"] for c in body]
            assert ids.index(dated) < ids.index(undated)
        finally:
            _cleanup([pid], [ws])

    def test_delivery_fields_are_present_and_inert(self, restore_client):
        """Modelled, returned, and doing nothing until P8.

        Serialised as stored rather than hidden: a field reading `not_dispatched` is
        honest, a silently withheld one is not.
        """
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("delivery")
        _member(pid, ws)
        cid = _seed_commitment(ws, _board_member(ws))
        try:
            body = _client(subject, ws).get(f"/api/commitments/{cid}").json()
            assert body["delivery_status"] == "not_dispatched"
            assert body["delivery_attempts"] == 0
            assert body["external_system"] is None
            assert body["external_task_id"] is None
        finally:
            _cleanup([pid], [ws])

    def test_due_date_serialises_as_a_calendar_day_not_a_timestamp(self, restore_client):
        """The TS type says `YYYY-MM-DD`. A deadline is a day, not an instant."""
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("date")
        _member(pid, ws)
        cid = _seed_commitment(ws, _board_member(ws), due_date=dt.date(2026, 9, 1))
        try:
            body = _client(subject, ws).get(f"/api/commitments/{cid}").json()
            assert body["due_date"] == "2026-09-01"
            assert "T" not in body["due_date"]
        finally:
            _cleanup([pid], [ws])
