"""Document reads and intake lifecycle endpoints (Meridian P3/P4).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

Verifies:
  - Clearance gate enforcement: documents above clearance are absent (404), never redacted.
  - Non-disclosure invariant: body text, content hash, and metadata never reach the client.
  - Multi-tenant isolation: documents in other workspaces are invisible.
  - Deduplication: tenant-scoped deduplication on (workspace_id, content_hash).
  - Option A atomic intake: embedding failure or Neo4j failure aborts with 503 and zero orphan records.
  - Audit logging: append-only audit event created on intake.
  - Quarantine reporting.
"""

from __future__ import annotations

import hashlib
import inspect
import os
import uuid
from unittest.mock import patch

import psycopg
import psycopg.rows
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip("set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests", allow_module_level=True)

from callosum import llm
from callosum.config import settings
from meridian import documents
from meridian.api import auth, errors
from meridian.api import documents as documents_api

pytestmark = pytest.mark.integration

#: The genuine `llm.embed`, captured at import — before the autouse `mock_llm_embed`
#: fixture below replaces it. `TestProviderBoundary` needs the real implementation:
#: asserting the boundary's behaviour against the stub that stands in for it would
#: prove nothing.
_REAL_EMBED = llm.embed

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


@pytest.fixture(autouse=True)
def stub_extraction(monkeypatch):
    """Stub the extractor, for the same reason `llm.embed` is stubbed — and it was missed.

    `intake_document` calls `extract.extract()` **once per chunk**, and the default
    provider is `gpt-oss:120b-cloud`: a cloud model reached over the internet. Measured
    on 2026-08-15, one call takes **15.3s**, and `OLLAMA_TIMEOUT` allows a 300s read. A
    dozen intake tests therefore meant minutes of model latency, answers that change run
    to run, and provider quota spent on every `pytest`.

    None of that was visible before, because the old code wrapped extraction in
    `except Exception: pass`. With no provider reachable, every call failed at the 5s
    connect timeout and was silently swallowed — which is why the suite was previously
    reported at 28s. It was fast because extraction never ran.

    `pyproject.toml` already draws this line: `addopts = "-m 'not llm'"` keeps live-model
    tests out of the default run. These tests are not marked `llm` and must therefore not
    reach a model. The stub returns a fixed verified edge plus one quarantined failure, so
    both `proposed_change` and `extraction_failure` still get exercised.
    """
    from callosum import extract
    from callosum.ontology import FailureReason, RelationType

    def _fake_extract(chunk_text: str):
        quote = chunk_text[: min(40, len(chunk_text))]
        rel = extract.Relationship(
            source="Test Source",
            type=RelationType.PROPOSED,
            target="Test Target",
            evidence=quote,
            confidence=0.9,
        )
        failure = extract.Failure(
            source="Bad Source",
            relation="PROPOSED",
            target="Bad Target",
            quote="a quote that is not in the chunk",
            confidence=0.5,
            reason=FailureReason.QUOTE_NOT_FOUND,
            detail="stubbed failure",
        )
        return extract.VerifiedExtraction(
            entities=[],
            relationships=[rel],
            spans={0: (0, len(quote))},
            failures=[failure],
        )

    monkeypatch.setattr(extract, "extract", _fake_extract)


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
                # Added by 0023_document_version. An exact-set assertion is the point of
                # this test: widening the document response is always a deliberate act,
                # and this line is where it gets acknowledged. `superseded_by_id` is
                # redacted per caller when the successor is above their clearance — see
                # `tests/test_document_versions.py`.
                "revision",
                "superseded_by_id",
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
            assert "Confidential" not in response.text
            assert "withheld" not in response.text.lower()
        finally:
            _cleanup([pid], [ws])

    def test_fetching_a_restricted_document_is_404_not_403(self, restore_client):
        """403 would confirm it exists. 404 is the same answer as 'no such document'."""
        client, pid, ws = _signed_in("oracle", INVESTOR)
        try:
            doc = _document(ws, "Confidential.pdf", CONFIDENTIAL)
            assert client.get(f"/api/documents/{doc}").status_code == 404
            assert client.get(f"/api/documents/{uuid.uuid4()}").status_code == 404
        finally:
            _cleanup([pid], [ws])

    def test_clearance_cannot_be_supplied_by_the_client(self, restore_client):
        """ADR-013: Clearance cannot be supplied as a query param."""
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
    """Making clearance required turns a forgotten argument into a TypeError.

    `list_quarantine` is in this list because it was once missing from it. It took no
    `clearance` at all, so every quarantine row in the workspace — quote, proposed graph
    fact and document id — was readable at any clearance. A default would have hidden
    that just as effectively as the missing parameter did.
    """
    for fn in (documents.list_documents, documents.get_document, documents.list_quarantine):
        parameter = inspect.signature(fn).parameters["clearance"]
        assert parameter.default is inspect.Parameter.empty, f"{fn.__name__} has a default clearance"


class TestIntakeLifecycle:
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

            # Assert raw_text and content_hash never leave in response
            assert "raw_text" not in data
            assert "content_hash" not in data

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

    def test_embedding_failure_fails_intake_without_zero_vectors(self, restore_client):
        client, pid, ws = _signed_in("fail_user", CONFIDENTIAL)
        try:
            # `EmbeddingProviderError`, not a bare `RuntimeError`: `llm.embed` is the
            # provider boundary and converts every backend failure into that one type,
            # so intake no longer wraps this call. A test that raises `RuntimeError`
            # here would be asserting a contract that moved.
            with patch("callosum.llm.embed", side_effect=llm.EmbeddingProviderError("Ollama offline")):
                payload = {
                    "title": "Offline Embedding Test",
                    "doc_type": "notes",
                    "raw_text": "Important text that must fail rather than be stored with zero vectors.",
                    "sensitivity": 1,
                }
                res = client.post("/api/documents/intake", json=payload)
                assert res.status_code == 503
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
            # Patches the underlying per-node write rather than the bridge helper, so
            # the failure enters through the same door a real Neo4j outage would.
            with patch("callosum.store.upsert_chunk_node", side_effect=RuntimeError("Neo4j down")):
                payload = {
                    "title": "Neo4j Down Test",
                    "doc_type": "notes",
                    "raw_text": "Text whose chunks fail to bridge to Neo4j.",
                    "sensitivity": 1,
                }
                res = client.post("/api/documents/intake", json=payload)
                assert res.status_code == 503
                assert res.json()["error"]["code"] == "service_unavailable"
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

            with psycopg.connect(settings().postgres_dsn, row_factory=psycopg.rows.dict_row) as conn:
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


SECRET_QUOTE = "The compensation committee agreed the number in closed session"


def _quarantine_row(ws: str, document_id: str, quote: str) -> None:
    """A rejected edge, as `queue_proposals` would have written it."""
    _admin(
        """
        INSERT INTO extraction_failure
            (workspace_id, document_id, source, relation, target, quote,
             confidence, reason, detail, provider, extractor_model)
        VALUES (%s, %s, 'Priya', 'RECEIVED', 'Compensation', %s,
                0.9, 'quote_not_found', 'paraphrase', 'ollama', 'test-model')
        """,
        (uuid.UUID(ws), uuid.UUID(document_id), quote),
    )


class TestQuarantineClearance:
    """The quarantine is a clearance-filtered surface, not an internal diagnostics feed.

    A row carries a quote, a proposed graph fact and a document id. Before this,
    `list_quarantine` took no `clearance` at all — RLS scoped the workspace and nothing
    scoped the clearance inside it.
    """

    def test_a_row_from_a_restricted_document_is_not_listed(self, restore_client):
        client, pid, ws = _signed_in("q_investor", INVESTOR)
        try:
            secret = _document(ws, "Compensation.pdf", CONFIDENTIAL)
            readable = _document(ws, "Minutes.pdf", PUBLIC)
            _quarantine_row(ws, secret, SECRET_QUOTE)
            _quarantine_row(ws, readable, "An ordinary sentence")

            body = client.get("/api/documents/quarantine").json()

            assert [r["document_id"] for r in body] == [readable]
        finally:
            _cleanup([pid], [ws])

    def test_the_restricted_quote_never_appears_in_the_payload(self, restore_client):
        """Asserted against the raw response, not the parsed rows.

        A leak that arrives in a field the test does not name is still a leak, so this
        checks the bytes on the wire rather than a key it remembered to look at.
        """
        client, pid, ws = _signed_in("q_leak", INVESTOR)
        try:
            secret = _document(ws, "Compensation.pdf", CONFIDENTIAL)
            _quarantine_row(ws, secret, SECRET_QUOTE)

            res = client.get("/api/documents/quarantine")

            assert res.status_code == 200
            assert SECRET_QUOTE not in res.text
            assert secret not in res.text
        finally:
            _cleanup([pid], [ws])

    def test_a_cleared_reader_still_sees_it(self, restore_client):
        """The filter must remove rows, not the feature."""
        client, pid, ws = _signed_in("q_confidential", CONFIDENTIAL)
        try:
            secret = _document(ws, "Compensation.pdf", CONFIDENTIAL)
            _quarantine_row(ws, secret, SECRET_QUOTE)

            body = client.get("/api/documents/quarantine").json()

            assert len(body) == 1
            assert body[0]["quote"] == SECRET_QUOTE
        finally:
            _cleanup([pid], [ws])

    def test_another_workspaces_quarantine_is_invisible(self, restore_client):
        client, pid, mine = _signed_in("q_mine", CONFIDENTIAL)
        theirs = _workspace("q_theirs")
        try:
            doc = _document(theirs, "Theirs.pdf", PUBLIC)
            _quarantine_row(theirs, doc, "Not yours")

            assert client.get("/api/documents/quarantine").json() == []
        finally:
            _cleanup([pid], [mine, theirs])


class TestProviderBoundary:
    """`llm.embed` converts backend failures into one type, so callers need not know.

    Without this, the only thing holding the contract asserted in
    `test_embedding_failure_fails_intake_without_zero_vectors` would be that test's own
    mock — which would keep passing if `embed` stopped raising `EmbeddingProviderError`
    tomorrow.
    """

    def test_an_arbitrary_provider_failure_becomes_embedding_provider_error(self, monkeypatch):
        import httpx

        def _boom(*a, **kw):
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(llm.httpx, "post", _boom)
        with pytest.raises(llm.EmbeddingProviderError):
            _REAL_EMBED(["some text"])

    def test_it_is_a_runtime_error_so_existing_callers_are_unaffected(self):
        """The CLI and eval paths already handle `RuntimeError` from this module."""
        assert issubclass(llm.EmbeddingProviderError, RuntimeError)


class TestDerivedIds:
    """Chunk ids are derived, so a crashed intake replays instead of orphaning nodes."""

    def test_the_same_document_in_the_same_workspace_yields_the_same_ids(self):
        ws = uuid.uuid4()
        a = documents._chunk_id(ws, "deadbeef", 0)
        b = documents._chunk_id(ws, "deadbeef", 0)
        assert a == b, "a retry must MERGE onto the same node, not mint a second one"

    def test_ordinals_do_not_collide(self):
        ws = uuid.uuid4()
        assert documents._chunk_id(ws, "deadbeef", 0) != documents._chunk_id(ws, "deadbeef", 1)

    def test_identical_content_in_two_workspaces_yields_different_ids(self):
        """The reason `workspace_id` is in the key rather than just the content hash.

        Migration `0022` scopes dedup to `(workspace_id, content_hash)` precisely so two
        tenants may hold byte-identical documents. Derive the id from the hash alone and
        those two tenants mint the same chunk ids — and `MERGE` fuses their bridge nodes
        into one. The migration that permits the duplicate would have created the leak.
        """
        ws_a, ws_b = uuid.uuid4(), uuid.uuid4()
        assert documents._chunk_id(ws_a, "deadbeef", 0) != documents._chunk_id(ws_b, "deadbeef", 0)
        assert documents._document_id(ws_a, "deadbeef") != documents._document_id(ws_b, "deadbeef")



# ---------------------------------------------------------------------------
# Sensitivity authorization (#143)
#
# The invariant: the ladder defined by the schema, intake validation and the
# authorization rules must be consistent, and intake must not create a
# less-protected state by default.
#
# Every read path in `meridian/documents.py` has always filtered on clearance,
# fail-closed. The write path consulted it nowhere. These three groups are the
# three ways that showed up.
# ---------------------------------------------------------------------------


class TestSensitivityCeiling:
    """Criterion 1 — a principal may not file above their own clearance."""

    def test_a_principal_cannot_file_above_their_clearance(self, restore_client):
        client, pid, ws = _signed_in("low", INVESTOR)  # clearance 1
        try:
            res = client.post(
                "/api/documents/intake",
                json={
                    "title": "Compensation Review",
                    "doc_type": "memo",
                    "raw_text": "Salary bands for the executive team.",
                    "sensitivity": CONFIDENTIAL,  # 3, above their 1
                },
            )
            assert res.status_code == 403
            assert res.json()["error"]["code"] == "forbidden"
        finally:
            _cleanup([pid], [ws])

    def test_the_refusal_is_a_refusal_and_not_a_clamp(self, restore_client):
        """The document must not exist at *any* level.

        A silent downgrade would be worse than the bug: the caller is told their
        document is confidential while it sits at investor level, readable by
        people they excluded. The listing is the check that matters — a 403 with
        a row behind it would still be a disclosure.
        """
        client, pid, ws = _signed_in("noclamp", INVESTOR)
        try:
            client.post(
                "/api/documents/intake",
                json={
                    "title": "Should Not Exist",
                    "doc_type": "memo",
                    "raw_text": "Filed above the caller's clearance.",
                    "sensitivity": CONFIDENTIAL,
                },
            )
            listing = client.get("/api/documents")
            assert listing.status_code == 200
            assert all(d["title"] != "Should Not Exist" for d in listing.json())
        finally:
            _cleanup([pid], [ws])

    def test_a_principal_may_file_at_or_below_their_clearance(self, restore_client):
        client, pid, ws = _signed_in("ok", CONFIDENTIAL)  # clearance 3
        try:
            for level in (PUBLIC, INVESTOR, 2, CONFIDENTIAL):
                res = client.post(
                    "/api/documents/intake",
                    json={
                        "title": f"Allowed At {level}",
                        "doc_type": "memo",
                        "raw_text": f"Distinct body for level {level} so dedup does not fire.",
                        "sensitivity": level,
                    },
                )
                assert res.status_code == 201, res.json()
                assert res.json()["sensitivity"] == level
        finally:
            _cleanup([pid], [ws])

    def test_the_refusal_names_the_authority_rule_not_the_comparison(self, restore_client):
        """An out-of-range value and an unauthorised one are different answers.

        A client that cannot tell them apart cannot tell the user whether to pick
        a lower level or to ask for clearance.
        """
        client, pid, ws = _signed_in("distinct", INVESTOR)
        try:
            unauthorised = client.post(
                "/api/documents/intake",
                json={"title": "A", "doc_type": "memo", "raw_text": "Body A.", "sensitivity": 3},
            )
            out_of_range = client.post(
                "/api/documents/intake",
                json={"title": "B", "doc_type": "memo", "raw_text": "Body B.", "sensitivity": 99},
            )
            assert unauthorised.status_code == 403
            assert out_of_range.status_code == 422
            assert unauthorised.json()["error"]["code"] != out_of_range.json()["error"]["code"]
        finally:
            _cleanup([pid], [ws])


class TestSensitivityIsRequired:
    """Criterion 2 — a missing classification is an error, never a public document."""

    def test_omitted_sensitivity_is_rejected(self, restore_client):
        client, pid, ws = _signed_in("omit", CONFIDENTIAL)
        try:
            res = client.post(
                "/api/documents/intake",
                json={
                    "title": "No Classification",
                    "doc_type": "memo",
                    "raw_text": "Filed without saying how sensitive it is.",
                },
            )
            assert res.status_code == 422
            # The same envelope an out-of-range value produces. A missing field must
            # not answer in a different format than an invalid one.
            assert res.json()["error"]["code"] == "invalid"
            assert "sensitivity" in res.json()["error"]["detail"]
        finally:
            _cleanup([pid], [ws])

    def test_omitting_sensitivity_does_not_create_a_public_document(self, restore_client):
        """The defect this criterion exists for.

        The field used to default to 0 — *public*, the widest visibility in the
        system — so omitting it published the document to everyone. The status
        code alone would not catch a regression here; the absence of the row is
        the assertion that matters.
        """
        client, pid, ws = _signed_in("nopublic", CONFIDENTIAL)
        try:
            client.post(
                "/api/documents/intake",
                json={
                    "title": "Unclassified Memo",
                    "doc_type": "memo",
                    "raw_text": "Confidential board matter filed without a level.",
                },
            )
            listing = client.get("/api/documents")
            assert all(d["title"] != "Unclassified Memo" for d in listing.json())
        finally:
            _cleanup([pid], [ws])


class TestReservedLevelFour:
    """Criterion 3 — `4 restricted` is reserved, and the gap is deliberate."""

    def test_level_four_is_not_creatable_through_intake(self, restore_client):
        client, pid, ws = _signed_in("founder", 4)
        try:
            res = client.post(
                "/api/documents/intake",
                json={
                    "title": "Founder Only",
                    "doc_type": "memo",
                    "raw_text": "Reserved tier.",
                    "sensitivity": 4,
                },
            )
            # 422, not 403: the caller's clearance is not the objection — the level
            # is not offered by intake at all, to anyone, pending the policy in #143.
            assert res.status_code == 422
            assert res.json()["error"]["code"] == "invalid"
        finally:
            _cleanup([pid], [ws])

    def test_the_gap_between_the_ladder_and_intake_is_exactly_one_reserved_level(self):
        """Guards the mismatch against becoming accidental again.

        `LADDER_LEVELS` mirrors `schema/postgres.sql`. If a level is added to the
        schema, or intake's accepted set is widened without a decision, this fails
        rather than the two drifting apart silently — which is how a documented
        five-level ladder ended up with a four-level intake that read as an
        off-by-one.
        """
        assert documents.LADDER_LEVELS == (0, 1, 2, 3, 4)
        assert documents.ACCEPTED_SENSITIVITIES == (0, 1, 2, 3)
        reserved = set(documents.LADDER_LEVELS) - set(documents.ACCEPTED_SENSITIVITIES)
        assert reserved == {4}, "level 4 is reserved by decision (#143); widening it needs the policy first"

# ---------------------------------------------------------------------------
# The dedup existence oracle is accepted and audited (ADR-016, #147 finding 1)
#
# Submitting content already filed in the workspace returns 409 whether or not the
# caller could read the existing document. That is a decision, not an oversight — the
# obvious repair does not work, and the alternatives cost more than the leak. What the
# decision requires is that the oracle leaves a trail.
# ---------------------------------------------------------------------------


def _audit_rows(ws: str, action: str) -> list[dict]:
    with psycopg.connect(settings().postgres_dsn, row_factory=psycopg.rows.dict_row) as conn:
        return conn.execute(
            "SELECT * FROM audit_event WHERE workspace_id = %s AND action = %s"
            " ORDER BY created_at",
            (uuid.UUID(ws), action),
        ).fetchall()


class TestDedupRefusalIsAudited:
    def test_a_hidden_collision_is_recorded_with_the_actor_and_the_hash(self, restore_client):
        """The case the oracle is about: a caller probes content filed above them.

        The 409 is unchanged — that is the accepted half of ADR-016. What must exist
        afterwards is the row that makes the probe visible.
        """
        client, pid, ws = _signed_in("prober", INVESTOR)  # clearance 1
        try:
            body = "A confidential memo the observer already holds a copy of."
            digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
            _admin(
                """
                INSERT INTO document (id, title, doc_type, raw_text, content_hash,
                                      sensitivity, workspace_id)
                VALUES (%s, %s, 'memo', %s, %s, %s, %s)
                """,
                (uuid.uuid4(), "Filed Above You", body, digest, CONFIDENTIAL, uuid.UUID(ws)),
            )

            res = client.post(
                "/api/documents/intake",
                json={"title": "Same Bytes", "doc_type": "memo",
                      "raw_text": body, "sensitivity": INVESTOR},
            )
            assert res.status_code == 409

            rows = _audit_rows(ws, "intake_duplicate_refused")
            assert len(rows) == 1
            payload = rows[0]["payload"]
            assert payload["content_hash"] == digest
            assert payload["actor_could_read"] is False
            assert payload["actor_clearance"] == INVESTOR
            assert str(rows[0]["actor_principal_id"]) == pid
        finally:
            _cleanup([pid], [ws])

    def test_a_visible_collision_is_recorded_too(self, restore_client):
        """Not only the hidden ones — otherwise the row's existence is the disclosure.

        If a refusal produced an audit row *only* when the actor could not read the
        original, then anyone able to read the trail could infer exactly what the 409
        was hiding. The distinction lives in the payload instead.
        """
        client, pid, ws = _signed_in("ordinary", CONFIDENTIAL)  # clearance 3
        try:
            body = "An ordinary duplicate the author can read perfectly well."
            first = client.post(
                "/api/documents/intake",
                json={"title": "First", "doc_type": "memo",
                      "raw_text": body, "sensitivity": PUBLIC},
            )
            assert first.status_code == 201

            again = client.post(
                "/api/documents/intake",
                json={"title": "Again", "doc_type": "memo",
                      "raw_text": body, "sensitivity": PUBLIC},
            )
            assert again.status_code == 409

            rows = _audit_rows(ws, "intake_duplicate_refused")
            assert len(rows) == 1
            assert rows[0]["payload"]["actor_could_read"] is True
        finally:
            _cleanup([pid], [ws])

    def test_the_refusal_still_discloses_nothing_beyond_the_409(self, restore_client):
        """Accepting the oracle is not licence to widen it.

        The caller learns that the content exists. They must not also learn the existing
        document's title, id, or the level it sits at.
        """
        client, pid, ws = _signed_in("bounded", INVESTOR)
        try:
            body = "Bytes filed above the caller, with a distinctive title elsewhere."
            secret_id = uuid.uuid4()
            _admin(
                """
                INSERT INTO document (id, title, doc_type, raw_text, content_hash,
                                      sensitivity, workspace_id)
                VALUES (%s, %s, 'memo', %s, %s, %s, %s)
                """,
                (secret_id, "Project Nightingale Compensation", body,
                 hashlib.sha256(body.encode("utf-8")).hexdigest(), CONFIDENTIAL, uuid.UUID(ws)),
            )

            res = client.post(
                "/api/documents/intake",
                json={"title": "Same Bytes", "doc_type": "memo",
                      "raw_text": body, "sensitivity": INVESTOR},
            )

            assert res.status_code == 409
            assert "Nightingale" not in res.text
            assert str(secret_id) not in res.text
            assert "sensitivity" not in res.text.lower()
        finally:
            _cleanup([pid], [ws])

    def test_a_successful_intake_records_no_refusal(self, restore_client):
        """Guards the obvious false positive: the row must mark a refusal, not any intake."""
        client, pid, ws = _signed_in("clean", CONFIDENTIAL)
        try:
            res = client.post(
                "/api/documents/intake",
                json={"title": "Novel", "doc_type": "memo",
                      "raw_text": "Content nothing else in this workspace has.",
                      "sensitivity": PUBLIC},
            )
            assert res.status_code == 201
            assert _audit_rows(ws, "intake_duplicate_refused") == []
        finally:
            _cleanup([pid], [ws])

    def test_a_failed_audit_does_not_turn_the_refusal_into_a_500(self, restore_client):
        """The trail is best-effort; the caller's answer is not.

        Losing the audit row is bad and is logged. Converting a correct 409 into a 500
        because the logging failed would be worse.
        """
        client, pid, ws = _signed_in("audit_down", CONFIDENTIAL)
        try:
            body = "Content submitted twice while auditing is broken."
            assert client.post(
                "/api/documents/intake",
                json={"title": "First", "doc_type": "memo",
                      "raw_text": body, "sensitivity": PUBLIC},
            ).status_code == 201

            with patch(
                "meridian.audit.record_audit_event",
                side_effect=RuntimeError("audit table unavailable"),
            ):
                again = client.post(
                    "/api/documents/intake",
                    json={"title": "Again", "doc_type": "memo",
                          "raw_text": body, "sensitivity": PUBLIC},
                )

            assert again.status_code == 409
            assert again.json()["error"]["code"] == "conflict"
        finally:
            _cleanup([pid], [ws])
