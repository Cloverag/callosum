"""The board-pack read endpoints (Meridian P3, CP-C — ADR-014).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

The highest-risk read path in the codebase. `list_packs` and `get_pack` take BOTH a
workspace and a **clearance**, and neither may come from the request — a client able
to name its own clearance could read every restricted document in the workspace.

The load-bearing test reads the SAME pack as two principals with different clearances
and asserts they see different items with contiguous positions both times. That is the
whole withholding contract in one assertion: filtered, renumbered, and nothing left
behind to count.
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
from meridian import meetings, packs
from meridian.api import auth, errors
from meridian.api import packs as packs_api

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
    application.include_router(packs_api.router)
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


def _member(principal_id: str, workspace_id: str, role: str = "founder") -> None:
    """`role`, not `clearance` (#166): effective clearance is derived from
    `membership.role` at read time — a stored `clearance` this helper's caller
    picked independently is inert. Default `'founder'` matches this file's old
    default (`clearance=4`).
    """
    _admin(
        "INSERT INTO membership (principal_id, workspace_id, role, clearance, active)"
        " VALUES (%s, %s, %s, %s, true)",
        (principal_id, workspace_id, role, identity.ROLE_TO_CLEARANCE[role]),
    )


def _document(workspace_id: str, title: str, sensitivity: int) -> str:
    """A document at a given sensitivity, inserted directly.

    `document` is in the frozen core schema with no product-side write path, which is
    why this goes through the admin connection rather than a domain function.
    """
    did = str(uuid.uuid4())
    _admin(
        """
        INSERT INTO document (id, title, doc_type, raw_text, content_hash, sensitivity, workspace_id)
        VALUES (%s, %s, 'memo', 'body', %s, %s, %s)
        """,
        (did, title, f"hash-{did}", sensitivity, workspace_id),
    )
    return did


def _seed_pack(workspace_id: str, docs: list[tuple[str, int]]) -> tuple[str, str]:
    """A published pack whose items interleave sensitivities.

    Interleaved on purpose: filtering at any level then removes items from the
    MIDDLE, so renumbering has to actually happen. Putting the restricted documents
    last would let a broken implementation pass.
    """
    m = meetings.create_meeting("Board Meeting", workspace_id=workspace_id)
    pack = packs.create_pack(m.id, "Q3 pack", workspace_id=workspace_id)
    for title, sensitivity in docs:
        packs.add_pack_item(
            pack.id, _document(workspace_id, title, sensitivity), workspace_id=workspace_id
        )
    return m.id, pack.id


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
        _admin("DELETE FROM board_pack_item WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM board_pack WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM meeting WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM document WHERE workspace_id = %s", (ws,))
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


class TestClearanceComesFromTheSession:
    def test_two_clearances_see_different_items_with_contiguous_positions(self, restore_client):
        """The whole withholding contract, in one test.

        The same pack, the same endpoint, two principals. The investor-clearance
        reader gets fewer items — and crucially their positions are 1..N with no gap,
        so nothing in the response reveals that anything was removed.
        """
        ws = _workspace("clr")
        _, pack_id = _seed_pack(
            ws,
            [
                ("Board deck", 1),
                ("Compensation review", 4),
                ("KPI pack", 1),
                ("Term sheet", 3),
                ("Pricing memo", 2),
            ],
        )
        hi_subject, lo_subject = f"sub-{uuid.uuid4()}", f"sub-{uuid.uuid4()}"
        hi, lo = _principal_with_identity(hi_subject), _principal_with_identity(lo_subject)
        _member(hi, ws, role="founder")
        _member(lo, ws, role="investor")
        try:
            founder = _client(hi_subject, ws).get(f"/api/packs/{pack_id}").json()
            investor = _client(lo_subject, ws).get(f"/api/packs/{pack_id}").json()

            assert len(founder["items"]) == 5
            assert len(investor["items"]) == 2

            # Contiguous for BOTH. A hole at position 2 would tell the investor that
            # a document exists between the deck and the KPI pack.
            for body in (founder, investor):
                positions = [i["position"] for i in body["items"]]
                assert positions == list(range(1, len(positions) + 1))

            # The restricted rows are absent, not redacted — nothing about them
            # appears in the payload in any form.
            blob = str(investor)
            assert "Compensation" not in blob and "Term sheet" not in blob
        finally:
            _cleanup([hi, lo], [ws])

    def test_the_same_item_has_a_different_position_per_reader(self, restore_client):
        """Which is why `position` is never an identity.

        Two readers, one row, two ordinals — the id is what is stable.
        """
        ws = _workspace("pos")
        _, pack_id = _seed_pack(ws, [("Deck", 1), ("Comp", 4), ("KPI", 1)])
        hi_subject, lo_subject = f"sub-{uuid.uuid4()}", f"sub-{uuid.uuid4()}"
        hi, lo = _principal_with_identity(hi_subject), _principal_with_identity(lo_subject)
        _member(hi, ws, role="founder")
        _member(lo, ws, role="investor")
        try:
            founder = _client(hi_subject, ws).get(f"/api/packs/{pack_id}").json()["items"]
            investor = _client(lo_subject, ws).get(f"/api/packs/{pack_id}").json()["items"]

            kpi_id = founder[2]["id"]
            assert founder[2]["position"] == 3
            same_row = next(i for i in investor if i["id"] == kpi_id)
            assert same_row["position"] == 2
        finally:
            _cleanup([hi, lo], [ws])

    def test_the_response_carries_no_total_to_subtract_from(self, restore_client):
        ws = _workspace("nototal")
        _, pack_id = _seed_pack(ws, [("Deck", 1), ("Comp", 4)])
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        _member(pid, ws, role="investor")
        try:
            body = _client(subject, ws).get(f"/api/packs/{pack_id}").json()
            for forbidden in ("item_count", "total_items", "withheld", "total"):
                assert forbidden not in body
        finally:
            _cleanup([pid], [ws])

    def test_a_demoted_reader_loses_items_on_the_next_request(self, restore_client):
        """Clearance is re-derived per request, so this needs no logout.

        `UPDATE membership SET role = ...`, not `clearance` (#166): a demotion is now
        a role change, and clearance follows it because it is derived, not stored.
        Updating the old `clearance` column directly — this test's original form —
        stopped doing anything the moment `identity.py` stopped reading it. Not a
        silent pass here: this file's fixtures were already fixed to a genuine
        `role="founder"` reader by the time this was reached, and a founder reading a
        level-4 document was correctly unaffected by an inert `clearance` UPDATE — the
        `assert ... == 1` after "demotion" failed loudly (`assert 2 == 1`, count
        unchanged) because nothing had actually demoted the reader.
        """
        ws = _workspace("demote")
        _, pack_id = _seed_pack(ws, [("Deck", 1), ("Comp", 4)])
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        _member(pid, ws, role="founder")
        try:
            client = _client(subject, ws)
            assert len(client.get(f"/api/packs/{pack_id}").json()["items"]) == 2

            _admin(
                "UPDATE membership SET role = 'investor' WHERE principal_id = %s AND workspace_id = %s",
                (pid, ws),
            )
            assert len(client.get(f"/api/packs/{pack_id}").json()["items"]) == 1
        finally:
            _cleanup([pid], [ws])


class TestReadsAndIsolation:
    def test_lists_packs_for_a_meeting(self, restore_client):
        ws = _workspace("list")
        mid, pack_id = _seed_pack(ws, [("Deck", 1)])
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        _member(pid, ws)
        try:
            body = _client(subject, ws).get("/api/packs", params={"meeting_id": mid}).json()
            assert [p["id"] for p in body] == [pack_id]
        finally:
            _cleanup([pid], [ws])

    def test_meeting_id_is_required(self, restore_client):
        ws = _workspace("req")
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        _member(pid, ws)
        try:
            assert _client(subject, ws).get("/api/packs").status_code == 422
        finally:
            _cleanup([pid], [ws])

    def test_another_workspaces_pack_is_not_found(self, restore_client):
        mine, theirs = _workspace("mine"), _workspace("theirs")
        _seed_pack(mine, [("Mine", 1)])
        _, other_pack = _seed_pack(theirs, [("Theirs", 1)])
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        _member(pid, mine)
        try:
            assert _client(subject, mine).get(f"/api/packs/{other_pack}").status_code == 404
        finally:
            _cleanup([pid], [mine, theirs])

    def test_the_wire_shape_matches_the_frontend_contract(self, restore_client):
        import re
        from pathlib import Path

        source = Path("frontend/src/lib/packs.ts").read_text()
        block = re.search(r"export type BoardPack = \{(.*?)\n\};", source, re.S)
        assert block
        ts_fields = set(re.findall(r"^\s{2}(\w+)\??:", block.group(1), re.M))

        ws = _workspace("shape")
        _, pack_id = _seed_pack(ws, [("Deck", 1)])
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        _member(pid, ws)
        try:
            body = _client(subject, ws).get(f"/api/packs/{pack_id}").json()
            assert set(body) == ts_fields, "the API response and lib/packs.ts have drifted"
        finally:
            _cleanup([pid], [ws])
