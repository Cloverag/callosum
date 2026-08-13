"""Document read and intake endpoints (Meridian P4).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

Verifies:
  - Document intake with chunking, embedding, and Neo4j chunk bridging.
  - Clearance gate enforcement: documents above clearance are completely absent/invisible.
  - Deduplication: identical content_hash within a workspace returns 409 Conflict.
  - Zero-vector rejection: embedding failure rejects intake without corrupting pgvector.
  - Neo4j bridge failure handling: graph store failures abort intake cleanly.
  - Quarantine listing endpoint.
"""

import os
import uuid
from unittest.mock import patch

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip("set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests", allow_module_level=True)

import hashlib
from callosum import llm
from callosum.config import settings
from meridian.api import auth, errors
from meridian.api import documents as documents_api

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


@pytest.fixture(autouse=True)
def mock_llm_embed(monkeypatch):
    """Provide deterministic test embeddings (1024-dim) in tests when live Ollama is offline."""
    def _deterministic_embed(texts: list[str], input_type: str = "document") -> list[list[float]]:
        vectors = []
        for t in texts:
            seed = int(hashlib.md5(t.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
            v = [0.001 * ((i + int(seed * 100)) % 10 + 1) for i in range(1024)]
            vectors.append(v)
        return vectors

    monkeypatch.setattr(llm, "embed", _deterministic_embed)


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
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM extraction_failure WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM proposed_change WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM chunk WHERE workspace_id = %s", (ws,))
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


class TestDocumentIntakeAndClearance:
    def test_list_documents_respects_clearance(self, restore_client):
        client, pid, ws = _signed_in("investor_user", INVESTOR)
        try:
            d_pub = _document(ws, "Public Notice", PUBLIC)
            d_inv = _document(ws, "Investor Update", INVESTOR)
            d_conf = _document(ws, "Comp Review", CONFIDENTIAL)

            res = client.get("/api/documents")
            assert res.status_code == 200
            ids = [d["id"] for d in res.json()]
            assert d_pub in ids
            assert d_inv in ids
            assert d_conf not in ids
        finally:
            _cleanup([pid], [ws])

    def test_get_document_above_clearance_returns_404(self, restore_client):
        client, pid, ws = _signed_in("investor_user", INVESTOR)
        try:
            d_conf = _document(ws, "Secret", CONFIDENTIAL)
            res = client.get(f"/api/documents/{d_conf}")
            assert res.status_code == 404
            assert res.json()["error"]["code"] == "not_found"
        finally:
            _cleanup([pid], [ws])

    def test_intake_document_success(self, restore_client):
        client, pid, ws = _signed_in("intake_user", CONFIDENTIAL)
        try:
            payload = {
                "title": "Q3 Board Strategy Deck",
                "doc_type": "transcript",
                "raw_text": "We discussed enterprise pricing tiers and agreed on $50k annual minimums.",
                "sensitivity": 2,
            }
            res = client.post("/api/documents/intake", json=payload)
            assert res.status_code == 201
            data = res.json()
            assert data["title"] == "Q3 Board Strategy Deck"
            assert data["doc_type"] == "transcript"
            assert data["sensitivity"] == 2

            # Verify it shows up in list_documents
            docs = client.get("/api/documents").json()
            assert any(d["id"] == data["id"] for d in docs)
        finally:
            _cleanup([pid], [ws])

    def test_intake_duplicate_hash_409(self, restore_client):
        client, pid, ws = _signed_in("dedupe_user", CONFIDENTIAL)
        try:
            payload = {
                "title": "Unique Document 1",
                "doc_type": "memo",
                "raw_text": "Identical document content for SHA-256 deduplication test.",
                "sensitivity": 1,
            }
            first = client.post("/api/documents/intake", json=payload)
            assert first.status_code == 201

            # Second intake with same raw_text in same workspace must yield 409
            dup = client.post("/api/documents/intake", json=payload)
            assert dup.status_code == 409
            err = dup.json()
            assert err["error"]["code"] == "conflict"
            assert "already exists in this workspace" in err["error"]["detail"]
        finally:
            _cleanup([pid], [ws])

    def test_intake_invalid_sensitivity_422(self, restore_client):
        client, pid, ws = _signed_in("user", CONFIDENTIAL)
        try:
            payload = {
                "title": "Bad Sensitivity",
                "doc_type": "memo",
                "raw_text": "Content",
                "sensitivity": 99,
            }
            res = client.post("/api/documents/intake", json=payload)
            assert res.status_code == 422
            assert res.json()["error"]["code"] == "invalid"
        finally:
            _cleanup([pid], [ws])

    def test_embedding_failure_fails_intake_without_zero_vectors(self, restore_client):
        client, pid, ws = _signed_in("fail_user", CONFIDENTIAL)
        try:
            with patch("callosum.llm.embed", side_effect=RuntimeError("Ollama offline")):
                payload = {
                    "title": "Offline Embedding Test",
                    "doc_type": "notes",
                    "raw_text": "Important text that must fail rather than be stored with zero vectors.",
                    "sensitivity": 1,
                }
                res = client.post("/api/documents/intake", json=payload)
                assert res.status_code == 422
                assert res.json()["error"]["code"] == "service_unavailable"

                # Assert no document or chunk exists
                with psycopg.connect(settings().postgres_dsn) as conn:
                    count = conn.execute(
                        "SELECT count(*) AS n FROM document WHERE title = 'Offline Embedding Test'"
                    ).fetchone()[0]
                    assert count == 0
        finally:
            _cleanup([pid], [ws])

    def test_neo4j_bridge_failure_fails_intake(self, restore_client):
        client, pid, ws = _signed_in("neo_fail_user", CONFIDENTIAL)
        try:
            with patch("callosum.store.upsert_chunk_node", side_effect=RuntimeError("Neo4j down")):
                payload = {
                    "title": "Neo4j Down Test",
                    "doc_type": "notes",
                    "raw_text": "Text whose chunks fail to bridge to Neo4j.",
                    "sensitivity": 1,
                }
                res = client.post("/api/documents/intake", json=payload)
                assert res.status_code == 422
                assert res.json()["error"]["code"] == "service_unavailable"
        finally:
            _cleanup([pid], [ws])

    def test_cross_workspace_identical_content_hash_allowed(self, restore_client):
        """Cross-tenant isolation: identical text in two different workspaces is allowed."""
        client_a, pid_a, ws_a = _signed_in("user_a", CONFIDENTIAL)
        client_b, pid_b, ws_b = _signed_in("user_b", CONFIDENTIAL)
        try:
            payload = {
                "title": "Shared Contract Template",
                "doc_type": "contract",
                "raw_text": "Standard mutual NDA agreement clauses across independent companies.",
                "sensitivity": 1,
            }
            res_a = client_a.post("/api/documents/intake", json=payload)
            assert res_a.status_code == 201

            # Same payload in workspace B succeeds (tenant isolation)
            res_b = client_b.post("/api/documents/intake", json=payload)
            assert res_b.status_code == 201

            # Duplicate in workspace A fails (409)
            res_a_dup = client_a.post("/api/documents/intake", json=payload)
            assert res_a_dup.status_code == 409
        finally:
            _cleanup([pid_a, pid_b], [ws_a, ws_b])

    def test_intake_empty_title_or_text_rejected(self, restore_client):
        client, pid, ws = _signed_in("user", CONFIDENTIAL)
        try:
            res_empty_title = client.post("/api/documents/intake", json={
                "title": "   ",
                "doc_type": "memo",
                "raw_text": "Valid text body.",
                "sensitivity": 1,
            })
            assert res_empty_title.status_code in (400, 422)

            res_empty_text = client.post("/api/documents/intake", json={
                "title": "Valid Title",
                "doc_type": "memo",
                "raw_text": "   ",
                "sensitivity": 1,
            })
            assert res_empty_text.status_code in (400, 422)
        finally:
            _cleanup([pid], [ws])

    def test_audit_event_recorded_on_intake(self, restore_client):
        client, pid, ws = _signed_in("audit_user", CONFIDENTIAL)
        try:
            payload = {
                "title": "Audit Verified Document",
                "doc_type": "memo",
                "raw_text": "This document must produce an append-only audit event upon intake.",
                "sensitivity": 1,
            }
            res = client.post("/api/documents/intake", json=payload)
            assert res.status_code == 201
            doc_id = res.json()["id"]

            with psycopg.connect(settings().postgres_dsn) as conn:
                events = conn.execute(
                    """
                    SELECT aggregate_type, aggregate_id, action, payload
                    FROM audit_event
                    WHERE workspace_id = %s AND aggregate_id = %s
                    """,
                    (uuid.UUID(ws), uuid.UUID(doc_id)),
                ).fetchall()
                assert len(events) == 1
                ev = events[0]
                assert ev["aggregate_type"] == "document"
                assert ev["action"] == "created"
                assert ev["payload"]["title"] == "Audit Verified Document"
                assert ev["payload"]["chunks_count"] >= 1
        finally:
            _cleanup([pid], [ws])

    def test_list_quarantine(self, restore_client):
        client, pid, ws = _signed_in("quarantine_user", CONFIDENTIAL)
        try:
            res = client.get("/api/documents/quarantine")
            assert res.status_code == 200
            assert isinstance(res.json(), list)
        finally:
            _cleanup([pid], [ws])
