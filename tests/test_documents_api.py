"""Document read endpoints (Meridian P3, CP-E).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

This closes the last mock sitting behind a live surface. The packs page fetched real
packs and mock documents, so every `board_pack_item.document_id` resolved to nothing
and every item rendered as "Document reference could not be resolved" — a live surface
making a false statement about real data.

The tests that matter are the clearance ones. A document above the caller's level must
be **absent**, not redacted, not counted, and not distinguishable from one that does
not exist.
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
from meridian.api import auth
from meridian.api import documents as documents_api
from meridian.api import errors

pytestmark = pytest.mark.integration

ISSUER = "https://keycloak.example/realms/meridian"

PUBLIC = 0
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
    application.include_router(documents_api.router)
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


def _principal_with_identity(subject: str, clearance: int) -> str:
    pid = str(uuid.uuid4())
    _admin(
        "INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, 'director', %s)",
        (pid, f"API User {pid[:6]}", clearance),
    )
    _admin(
        "INSERT INTO principal_identity (principal_id, provider, subject) VALUES (%s, %s, %s)",
        (pid, ISSUER, subject),
    )
    return pid


def _member(principal_id: str, workspace_id: str, clearance: int) -> None:
    _admin(
        "INSERT INTO membership (principal_id, workspace_id, role, clearance, active)"
        " VALUES (%s, %s, 'director', %s, true)",
        (principal_id, workspace_id, clearance),
    )


def _document(ws: str, title: str, sensitivity: int, doc_type: str = "board_deck") -> str:
    doc_id = str(uuid.uuid4())
    _admin(
        """
        INSERT INTO document (id, title, doc_type, raw_text, content_hash, sensitivity, workspace_id)
        VALUES (%s, %s, %s, 'Body text that must never reach a browser', %s, %s, %s)
        """,
        (uuid.UUID(doc_id), title, doc_type, doc_id, sensitivity, uuid.UUID(ws)),
    )
    return doc_id


def _cleanup(principal_ids: list[str], workspace_ids: list[str]) -> None:
    for ws in workspace_ids:
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


def _signed_in(label: str, clearance: int) -> tuple[TestClient, str, str]:
    subject = f"sub-{uuid.uuid4()}"
    pid = _principal_with_identity(subject, clearance)
    ws = _workspace(label)
    _member(pid, ws, clearance)
    return _client(subject, ws), pid, ws


class TestReads:
    def test_lists_documents_newest_ingestion_first(self, restore_client):
        client, pid, ws = _signed_in("list", CONFIDENTIAL)
        try:
            _document(ws, "Older.pdf", PUBLIC)
            _document(ws, "Newer.pdf", PUBLIC)
            body = client.get("/api/documents").json()
            assert [d["title"] for d in body] == ["Newer.pdf", "Older.pdf"]
        finally:
            _cleanup([pid], [ws])

    def test_filters_by_doc_type(self, restore_client):
        client, pid, ws = _signed_in("bytype", CONFIDENTIAL)
        try:
            _document(ws, "Deck.pdf", PUBLIC, doc_type="board_deck")
            _document(ws, "Notes.txt", PUBLIC, doc_type="transcript")
            body = client.get("/api/documents", params={"doc_type": "transcript"}).json()
            assert [d["title"] for d in body] == ["Notes.txt"]
        finally:
            _cleanup([pid], [ws])

    def test_never_returns_the_document_body(self, restore_client):
        """`raw_text`, `content_hash` and `metadata` are excluded in the SQL.

        A board surface renders a document's identity, not the corpus. These are left
        out of the query rather than dropped in Python, so they never leave the
        database at all.
        """
        client, pid, ws = _signed_in("nobody", CONFIDENTIAL)
        try:
            _document(ws, "Deck.pdf", PUBLIC)
            body = client.get("/api/documents").json()
            assert set(body[0]) == {
                "id",
                "title",
                "doc_type",
                "source_uri",
                "sensitivity",
                "authored_at",
                "ingested_at",
            }
            assert "must never reach a browser" not in client.get("/api/documents").text
        finally:
            _cleanup([pid], [ws])


class TestClearance:
    """A document above the caller's level is absent, not redacted."""

    def test_a_restricted_document_is_not_listed(self, restore_client):
        client, pid, ws = _signed_in("filter", INVESTOR)
        try:
            _document(ws, "Public.pdf", PUBLIC)
            _document(ws, "Confidential.pdf", CONFIDENTIAL)
            response = client.get("/api/documents")
            body = response.json()
            assert [d["title"] for d in body] == ["Public.pdf"]
            # No count, no placeholder, no total to subtract from.
            assert "Confidential" not in response.text
            assert "withheld" not in response.text.lower()
        finally:
            _cleanup([pid], [ws])

    def test_fetching_a_restricted_document_is_404_not_403(self, restore_client):
        """403 would confirm it exists. 404 is the same answer as "no such document"."""
        client, pid, ws = _signed_in("oracle", INVESTOR)
        try:
            doc = _document(ws, "Confidential.pdf", CONFIDENTIAL)
            assert client.get(f"/api/documents/{doc}").status_code == 404
            # And a genuinely absent id answers identically.
            assert client.get(f"/api/documents/{uuid.uuid4()}").status_code == 404
        finally:
            _cleanup([pid], [ws])

    def test_clearance_cannot_be_supplied_by_the_client(self, restore_client):
        """The mock took a `clearance` argument because it filtered its own data.

        The real endpoint does not, and asking for one changes nothing — an unknown
        query parameter is ignored by FastAPI, so the caller gets their own clearance
        rather than the one they asked for.
        """
        client, pid, ws = _signed_in("noclearance", INVESTOR)
        try:
            _document(ws, "Public.pdf", PUBLIC)
            _document(ws, "Confidential.pdf", CONFIDENTIAL)
            body = client.get("/api/documents", params={"clearance": "4"}).json()
            assert [d["title"] for d in body] == ["Public.pdf"]
        finally:
            _cleanup([pid], [ws])

    def test_a_document_in_another_workspace_is_invisible(self, restore_client):
        client, pid, mine = _signed_in("mine", CONFIDENTIAL)
        theirs = _workspace("theirs")
        try:
            doc = _document(theirs, "Not yours.pdf", PUBLIC)
            assert client.get("/api/documents").json() == []
            assert client.get(f"/api/documents/{doc}").status_code == 404
        finally:
            _cleanup([pid], [mine, theirs])


def test_the_clearance_argument_has_no_default(restore_client):
    """The defect this module was written to avoid repeating.

    `packs.list_packs` shipped with `clearance: int = 4` — the top of the ladder — so
    any caller who forgot the argument received everything. Making it required turns a
    forgotten argument into a `TypeError` at the call site instead of a silent
    disclosure.
    """
    import inspect

    from meridian import documents

    for fn in (documents.list_documents, documents.get_document):
        parameter = inspect.signature(fn).parameters["clearance"]
        assert parameter.default is inspect.Parameter.empty, f"{fn.__name__} has a default clearance"
