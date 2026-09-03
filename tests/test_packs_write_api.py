"""Board pack write endpoints (Meridian P3, CP-D — D2b).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

**The highest-risk write path in the codebase.** Four of the seven write functions take
a required `clearance` and all four return the pack, and returning a pack means
returning its items — so a write that accepted a client-supplied clearance would be the
read vulnerability wearing a write endpoint as a disguise.

The two tests that matter most here are not the CRUD ones:

- `test_a_write_response_is_clearance_filtered` — a low-clearance member edits a pack
  containing a restricted document and the response omits it, with no count and no gap
  in `position` to subtract from. The CP3 discipline has to survive the write path, not
  just the read path.
- `test_clearance_cannot_be_supplied_by_the_client` — the ADR-013 rule, asserted over
  HTTP rather than only in the schema guard.
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
from meridian.api import auth, errors
from meridian.api import packs as packs_api

pytestmark = pytest.mark.integration

ISSUER = "https://keycloak.example/realms/meridian"

#: Clearance ladder, named rather than spelled as integers. `1` is investor and `3` is
#: confidential — the p1.0.5 postmortem records a fail-open caused by reading `1` as
#: "public", so these are not written as bare numbers here.
INVESTOR = 1
CONFIDENTIAL = 3


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


def _principal_with_identity(subject: str, role: str) -> str:
    pid = str(uuid.uuid4())
    _admin(
        "INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, %s, %s)",
        (pid, f"API User {pid[:6]}", role, identity.ROLE_TO_CLEARANCE[role]),
    )
    _admin(
        "INSERT INTO principal_identity (principal_id, provider, subject) VALUES (%s, %s, %s)",
        (pid, ISSUER, subject),
    )
    return pid


def _member(principal_id: str, workspace_id: str, role: str) -> None:
    """`role`, not `clearance` (#166): effective clearance is derived from
    `membership.role` at read time.
    """
    _admin(
        "INSERT INTO membership (principal_id, workspace_id, role, clearance, active)"
        " VALUES (%s, %s, %s, %s, true)",
        (principal_id, workspace_id, role, identity.ROLE_TO_CLEARANCE[role]),
    )


def _document(ws: str, title: str, sensitivity: int) -> str:
    doc_id = str(uuid.uuid4())
    _admin(
        """
        INSERT INTO document (id, title, doc_type, raw_text, content_hash, sensitivity, workspace_id)
        VALUES (%s, %s, 'board_deck', 'Body text', %s, %s, %s)
        """,
        (uuid.UUID(doc_id), title, doc_id, sensitivity, uuid.UUID(ws)),
    )
    return doc_id


def _cleanup(principal_ids: list[str], workspace_ids: list[str]) -> None:
    for ws in workspace_ids:
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM board_pack_item WHERE workspace_id = %s", (ws,))
        _admin("UPDATE board_pack SET superseded_by_id = NULL WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM board_pack WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM document WHERE workspace_id = %s", (ws,))
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
    def __init__(self, label: str, role: str = "director"):
        self.subject = f"sub-{uuid.uuid4()}"
        self.pid = _principal_with_identity(self.subject, role)
        self.ws = _workspace(label)
        _member(self.pid, self.ws, role)
        self.meeting = meetings.create_meeting("Board Meeting", workspace_id=self.ws)
        self.client = _client(self.subject, self.ws)
        self.extra_pids: list[str] = []

    def pack(self, title: str = "November pack") -> dict:
        response = self.client.post(
            "/api/packs", json={"meeting_id": self.meeting.id, "title": title}
        )
        assert response.status_code == 201, response.text
        return response.json()

    def add(self, pack: dict, doc_id: str, **kw) -> dict:
        response = self.client.post(
            f"/api/packs/{pack['id']}/items", json={"document_id": doc_id, **kw}
        )
        assert response.status_code == 201, response.text
        return response.json()

    def reread(self, pack: dict) -> dict:
        """Adding an item bumps the pack's version, so the create response goes stale."""
        return self.client.get(f"/api/packs/{pack['id']}").json()

    def member_at(self, role: str) -> TestClient:
        """A second signed-in member of the same workspace at a different role."""
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject, role)
        _member(pid, self.ws, role)
        self.extra_pids.append(pid)
        return _client(subject, self.ws)

    def close(self):
        _cleanup([self.pid, *self.extra_pids], [self.ws])


class TestCreateAndEdit:
    def test_creates_a_draft_pack(self, restore_client):
        f = _Fixture("create")
        try:
            body = f.pack()
            assert body["status"] == "draft"
            assert body["items"] == []
        finally:
            f.close()

    def test_a_stale_patch_is_409(self, restore_client):
        f = _Fixture("stale")
        try:
            p = f.pack()
            f.client.patch(
                f"/api/packs/{p['id']}",
                json={"expected_version": p["version"], "title": "First"},
            )
            conflict = f.client.patch(
                f"/api/packs/{p['id']}",
                json={"expected_version": p["version"], "title": "Second"},
            )
            assert conflict.status_code == 409
            assert conflict.json()["error"]["code"] == "stale_resource"
        finally:
            f.close()

    def test_clearance_cannot_be_supplied_by_the_client(self, restore_client):
        """ADR-013 over HTTP.

        The OpenAPI guard proves clearance is not *declared* anywhere. This proves that
        sending it anyway is refused rather than quietly honoured.
        """
        f = _Fixture("clearance")
        try:
            p = f.pack()
            response = f.client.patch(
                f"/api/packs/{p['id']}",
                json={"expected_version": p["version"], "title": "X", "clearance": 4},
            )
            assert response.status_code == 422
        finally:
            f.close()


class TestItems:
    def test_adds_and_removes_items_closing_the_gap(self, restore_client):
        f = _Fixture("items")
        try:
            p = f.pack()
            first = f.add(p, _document(f.ws, "One.pdf", 0))
            middle = f.add(p, _document(f.ws, "Two.pdf", 0))
            last = f.add(p, _document(f.ws, "Three.pdf", 0))
            assert [i["position"] for i in (first, middle, last)] == [1, 2, 3]

            assert f.client.delete(f"/api/packs/items/{middle['id']}").status_code == 204

            items = f.client.get(f"/api/packs/{p['id']}").json()["items"]
            assert [i["id"] for i in items] == [first["id"], last["id"]]
            assert [i["position"] for i in items] == [1, 2]
        finally:
            f.close()

    def test_a_published_pack_refuses_new_items(self, restore_client):
        """The guard that replaces `expected_version` here.

        A published pack is frozen; amending it means a new version. There is no
        version of this call that succeeds, which is stronger than a counter.
        """
        f = _Fixture("frozen")
        try:
            p = f.pack()
            f.add(p, _document(f.ws, "One.pdf", 0))
            current = f.reread(p)
            published = f.client.post(
                f"/api/packs/{p['id']}/publish", json={"expected_version": current["version"]}
            )
            assert published.status_code == 200
            assert published.json()["status"] == "published"

            refused = f.client.post(
                f"/api/packs/{p['id']}/items",
                json={"document_id": _document(f.ws, "Late.pdf", 0)},
            )
            assert refused.status_code == 409
        finally:
            f.close()

    def test_a_published_pack_refuses_edits(self, restore_client):
        f = _Fixture("frozenedit")
        try:
            p = f.pack()
            published = f.client.post(
                f"/api/packs/{p['id']}/publish", json={"expected_version": p["version"]}
            ).json()
            refused = f.client.patch(
                f"/api/packs/{p['id']}",
                json={"expected_version": published["version"], "title": "Renamed"},
            )
            assert refused.status_code == 409
        finally:
            f.close()


class TestClearanceSurvivesTheWritePath:
    """The reason this module gets its own scrutiny."""

    def test_a_write_response_is_clearance_filtered(self, restore_client):
        """A write must not reveal what a read would have withheld.

        The pack holds one public and one confidential document. An investor-clearance
        member renames the pack — a legitimate edit — and the response must contain only
        the public item, renumbered from 1.

        **Amended for ADR-018.** This test previously asserted `"withheld" not in
        response`, encoding the doctrine that a pack discloses nothing at all. ADR-018
        reverses that half: the count is disclosed, because a published pack claims to be
        the material for a meeting and a director preparing from a silently truncated one
        is the harm. The renumbering is unchanged and still asserted — it closes a covert
        channel that the count does not reopen.

        The replacement is strictly stronger than what it replaces: the restricted
        document's id and title are now checked against the **raw body**, not just the
        parsed `items`, so a leak through any field fails here.
        """
        f = _Fixture("filtered")
        try:
            p = f.pack()
            restricted_doc = _document(f.ws, "Restricted.pdf", CONFIDENTIAL)
            public_doc = _document(f.ws, "Public.pdf", 0)
            f.add(p, restricted_doc)
            f.add(p, public_doc)

            investor = f.member_at("investor")
            current = investor.get(f"/api/packs/{p['id']}").json()
            patched = investor.patch(
                f"/api/packs/{p['id']}",
                json={"expected_version": current["version"], "title": "Renamed by investor"},
            )
            assert patched.status_code == 200
            items = patched.json()["items"]

            visible_docs = [i["document_id"] for i in items]
            assert restricted_doc not in visible_docs
            assert visible_docs == [public_doc]
            # Renumbered from 1: a gap would announce the rank of what was removed.
            assert [i["position"] for i in items] == [1]
            # The count IS disclosed (ADR-018) — one item, and it is right.
            assert patched.json()["withheld_items"] == 1
            # And it is the ONLY thing disclosed about it. Raw body, not parsed fields:
            # a title or id reaching any part of the response fails here.
            assert restricted_doc not in patched.text
            assert "Restricted.pdf" not in patched.text
        finally:
            f.close()

    def test_publishing_does_not_widen_what_the_publisher_sees(self, restore_client):
        f = _Fixture("publishfilter")
        try:
            p = f.pack()
            f.add(p, _document(f.ws, "Restricted.pdf", CONFIDENTIAL))
            public_doc = _document(f.ws, "Public.pdf", 0)
            f.add(p, public_doc)

            investor = f.member_at("investor")
            current = investor.get(f"/api/packs/{p['id']}").json()
            published = investor.post(
                f"/api/packs/{p['id']}/publish", json={"expected_version": current["version"]}
            )
            assert published.status_code == 200
            visible_docs = [i["document_id"] for i in published.json()["items"]]
            assert visible_docs == [public_doc]
        finally:
            f.close()


class TestSupersede:
    def test_returns_both_halves_and_copies_items_forward(self, restore_client):
        f = _Fixture("supersede")
        try:
            p = f.pack("Original pack")
            f.add(p, _document(f.ws, "One.pdf", 0))
            published = f.client.post(
                f"/api/packs/{p['id']}/publish",
                json={"expected_version": f.reread(p)["version"]},
            ).json()

            response = f.client.post(
                f"/api/packs/{p['id']}/supersede",
                json={"new_title": "Revised pack", "expected_version": published["version"]},
            )
            assert response.status_code == 201
            body = response.json()

            assert body["replacement"]["title"] == "Revised pack"
            assert body["superseded"]["id"] == p["id"]
            assert len(body["replacement"]["items"]) == 1, "items were not copied forward"

            # A superseded pack keeps status `published` and is identified by
            # `superseded_by_id`. There is deliberately no `superseded` status:
            # `PACK_STATUSES` is `{draft, published}` and `frontend/src/lib/packs.ts`
            # agrees. Same rule as #58 decision 1 for resolutions — the pointer already
            # says it, and a status would be a second way to say the same thing that
            # could disagree with the first.
            assert body["superseded"]["status"] == "published"
            assert body["superseded"]["superseded_by_id"] == body["replacement"]["id"]
            assert body["replacement"]["version_no"] > body["superseded"]["version_no"]

            # The superseded pack is still readable — a trail, not a deletion.
            assert f.client.get(f"/api/packs/{p['id']}").status_code == 200
        finally:
            f.close()


class TestReorder:
    def test_reorders_a_draft_pack(self, restore_client):
        f = _Fixture("reorder")
        try:
            p = f.pack()
            a = f.add(p, _document(f.ws, "A.pdf", 0))
            b = f.add(p, _document(f.ws, "B.pdf", 0))
            response = f.client.post(
                f"/api/packs/{p['id']}/reorder",
                json={"ordered_item_ids": [b["id"], a["id"]]},
            )
            assert response.status_code == 200
            assert [i["id"] for i in response.json()["items"]] == [b["id"], a["id"]]
        finally:
            f.close()

    def test_a_reorder_from_a_filtered_view_is_refused(self, restore_client):
        """Not a bug to route around — the honest failure.

        A low-clearance caller cannot see every item, so they cannot send every id. The
        domain refuses an incomplete list rather than silently dropping the items they
        could not see, which would delete restricted content from a pack by omission.
        """
        f = _Fixture("filteredreorder")
        try:
            p = f.pack()
            f.add(p, _document(f.ws, "Restricted.pdf", CONFIDENTIAL))
            f.add(p, _document(f.ws, "Public.pdf", 0))

            investor = f.member_at("investor")
            visible = investor.get(f"/api/packs/{p['id']}").json()["items"]
            assert len(visible) == 1

            response = investor.post(
                f"/api/packs/{p['id']}/reorder",
                json={"ordered_item_ids": [visible[0]["id"]]},
            )
            assert response.status_code in (409, 422)
        finally:
            f.close()
