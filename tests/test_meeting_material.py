"""Material assigned to a meeting, and what it discloses (Meridian P4, ADR-018).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

Material is a **completeness claim** — "this is the material for this meeting" — so under
ADR-018 it discloses a count of what the caller may not read. That makes the count the
one thing this surface is *supposed* to leak, and everything else the thing it must not:
a title, an id, a date, a doc_type, an ordinal.

So the withholding tests assert against the **raw response body**, not against parsed
fields. A title reaching an unexpected key is exactly the failure a field-by-field
assertion misses, and it is the failure that actually happened once already — `0024`'s
`superseded_by_id` leaked a withheld revision id through three surfaces at once.

Harness mirrors `tests/test_document_versions.py`.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid

import psycopg
import psycopg.rows
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip("set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests", allow_module_level=True)

from callosum import identity, llm
from callosum.config import settings
from meridian import documents
from meridian.api import auth, errors
from meridian.api import documents as documents_api
from meridian.api import meetings as meetings_api

pytestmark = pytest.mark.integration

ISSUER = "https://keycloak.example/realms/meridian"

PUBLIC = 0
INVESTOR = 1
INTERNAL = 2
CONFIDENTIAL = 3


# --- Harness (mirrors tests/test_documents_api.py) ---------------------------


def _admin(sql: str, params: tuple = ()) -> None:
    with psycopg.connect(settings().postgres_dsn) as conn:
        conn.execute(sql, params)
        conn.commit()


def _admin_rows(sql: str, params: tuple = ()) -> list[dict]:
    with psycopg.connect(settings().postgres_dsn, row_factory=psycopg.rows.dict_row) as conn:
        return conn.execute(sql, params).fetchall()


class _StubClient:
    def __init__(self, claims):
        self._claims = claims

    async def authorize_access_token(self, request):
        return {"userinfo": self._claims}


@pytest.fixture(autouse=True)
def mock_llm_embed(monkeypatch):
    """Deterministic 1024-dim embeddings, so intake never reaches a provider."""

    def _deterministic_embed(texts: list[str], input_type: str = "document") -> list[list[float]]:
        vectors = []
        for t in texts:
            seed = int(hashlib.md5(t.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
            vectors.append([0.001 * ((i + int(seed * 100)) % 10 + 1) for i in range(1024)])
        return vectors

    monkeypatch.setattr(llm, "embed", _deterministic_embed)


@pytest.fixture(autouse=True)
def stub_extraction(monkeypatch):
    """Stub the extractor. Supersession calls intake, and intake extracts per chunk."""
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
        return extract.VerifiedExtraction(entities=[], relationships=[rel], spans={0: (0, len(quote))}, failures=[failure])

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
    application.include_router(meetings_api.router)
    errors.install_exception_handlers(application)
    auth._client = lambda request: _StubClient({"sub": subject, "iss": ISSUER})  # type: ignore[assignment]
    return application


def _workspace(label: str) -> str:
    ws = str(uuid.uuid4())
    _admin("INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s)", (ws, f"{label}-{ws[:6]}", ws))
    return ws


def _principal_with_identity(subject: str, role: str) -> str:
    pid = str(uuid.uuid4())
    _admin("INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, %s, %s)", (pid, f"User {pid[:6]}", role, identity.ROLE_TO_CLEARANCE[role]))
    _admin("INSERT INTO principal_identity (principal_id, provider, subject) VALUES (%s, %s, %s)", (pid, ISSUER, subject))
    return pid


def _member(principal_id: str, workspace_id: str, role: str) -> None:
    """`role`, not `clearance` (#166): effective clearance is derived from
    `membership.role` at read time. This file's two-reader (`_signed_in`/`_joins`)
    withholding tests are exactly the shape that broke when both readers hardcoded
    `role='director'` while only their stored `clearance` differed.
    """
    _admin(
        "INSERT INTO membership (principal_id, workspace_id, role, clearance, active) VALUES (%s, %s, %s, %s, true)",
        (principal_id, workspace_id, role, identity.ROLE_TO_CLEARANCE[role]),
    )


def _cleanup(principal_ids: list[str], workspace_ids: list[str]) -> None:
    for ws in workspace_ids:
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
        # Before the documents: `meeting_document` cascades from both parents, but the
        # meeting itself has to go before the workspace can.
        _admin("DELETE FROM meeting_document WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM meeting WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM extraction_failure WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM proposed_change WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM chunk WHERE workspace_id = %s", (ws,))
        # The chain must be broken before the rows go, or the self-FK refuses the delete
        # for every document that some other revision still names.
        _admin("UPDATE document SET superseded_by_id = NULL WHERE workspace_id = %s", (ws,))
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


def _signed_in(label: str, role: str) -> tuple[TestClient, str, str]:
    subject = f"sub-{uuid.uuid4()}"
    pid = _principal_with_identity(subject, role)
    ws = _workspace(label)
    _member(pid, ws, role)
    return _client(subject, ws), pid, ws


def _joins(ws: str, role: str) -> tuple[TestClient, str]:
    """A second signed-in principal in an EXISTING workspace, at a different role.

    Every withholding test needs two readers of one chain. The principal is returned so
    the caller can hand it to the *same* `_cleanup` as the first: a principal who has
    authored a document cannot be deleted before that document is, and
    `document_authored_by_fkey` refuses rather than cascading. Cleaning them separately
    is what the first draft of this file did, and all five two-reader tests failed on it.
    """
    subject = f"sub-{uuid.uuid4()}"
    pid = _principal_with_identity(subject, role)
    _member(pid, ws, role)
    return _client(subject, ws), pid


def _intake(client: TestClient, title: str, text: str, sensitivity: int) -> dict:
    res = client.post(
        "/api/documents/intake",
        json={"title": title, "doc_type": "memo", "raw_text": text, "sensitivity": sensitivity},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _meeting(client: TestClient, title: str = "Q3 Board Meeting") -> str:
    res = client.post("/api/meetings", json={"title": title})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _assign(client: TestClient, meeting_id: str, document_id: str):
    return client.post(f"/api/meetings/{meeting_id}/material", json={"document_id": document_id})


def _material(client: TestClient, meeting_id: str):
    return client.get(f"/api/meetings/{meeting_id}/material")


# --- The happy path ----------------------------------------------------------


class TestAssign:
    def test_assign_then_read_back(self, restore_client):
        client, pid, ws = _signed_in("material", "director")
        try:
            doc = _intake(client, "Vendor contract", "Northwind terms.", INVESTOR)
            meeting = _meeting(client)

            res = _assign(client, meeting, doc["id"])
            assert res.status_code == 201, res.text
            body = res.json()
            assert [d["id"] for d in body["documents"]] == [doc["id"]]
            assert body["withheld"] == 0

            assert _material(client, meeting).json() == body
        finally:
            _cleanup([pid], [ws])

    def test_material_is_ordered_by_assignment_not_by_ingestion(self, restore_client):
        """Assignment order is the board's; ingestion order is the filing system's.

        A director reading a meeting's material sees it in the order someone decided it
        belonged there, which is the only order this table records.
        """
        client, pid, ws = _signed_in("order", "director")
        try:
            first = _intake(client, "Filed first", "one", INVESTOR)
            second = _intake(client, "Filed second", "two", INVESTOR)
            meeting = _meeting(client)

            _assign(client, meeting, second["id"])
            _assign(client, meeting, first["id"])

            assert [d["title"] for d in _material(client, meeting).json()["documents"]] == [
                "Filed second",
                "Filed first",
            ]
        finally:
            _cleanup([pid], [ws])


# --- Refusals ----------------------------------------------------------------


class TestRefusals:
    def test_assigning_twice_is_a_conflict(self, restore_client):
        client, pid, ws = _signed_in("dupe", "director")
        try:
            doc = _intake(client, "Contract", "terms", INVESTOR)
            meeting = _meeting(client)
            assert _assign(client, meeting, doc["id"]).status_code == 201
            assert _assign(client, meeting, doc["id"]).status_code == 409
        finally:
            _cleanup([pid], [ws])

    def test_a_document_above_clearance_answers_404_not_403(self, restore_client):
        """The existence oracle stays closed.

        Document ids are derivable from candidate plaintext (`_document_id` is uuid5 over
        a public namespace constant), so a 403 here would let a holder of a leaked memo
        confirm the board holds it without reading anything. Same rule as
        `supersede_document`'s predecessor lookup.
        """
        client, pid, ws = _signed_in("oracle", "director")
        low, low_pid = _joins(ws, "investor")
        try:
            secret = _intake(client, "Board comp memo", "salaries", CONFIDENTIAL)
            meeting = _meeting(client)

            res = _assign(low, meeting, secret["id"])
            assert res.status_code == 404, res.text
            assert "clearance" not in res.text.lower()
            assert "Board comp memo" not in res.text
        finally:
            _cleanup([pid, low_pid], [ws])

    def test_a_missing_document_and_a_hidden_one_answer_identically(self, restore_client):
        """The two refusals must be indistinguishable, or the pair IS the oracle.

        Answering 404 for a hidden document is worth nothing if a document that simply
        does not exist answers something else — the difference is the disclosure.
        """
        client, pid, ws = _signed_in("same", "director")
        low, low_pid = _joins(ws, "investor")
        try:
            secret = _intake(client, "Hidden", "text", CONFIDENTIAL)
            meeting = _meeting(client)

            hidden = _assign(low, meeting, secret["id"])
            absent = _assign(low, meeting, str(uuid.uuid4()))
            assert hidden.status_code == absent.status_code == 404
            assert hidden.json() == absent.json()
        finally:
            _cleanup([pid, low_pid], [ws])

    def test_a_meeting_in_another_workspace_cannot_be_given_material(self, restore_client):
        """Tenancy, proved rather than assumed."""
        client, pid, ws = _signed_in("mine", "director")
        other, other_pid, other_ws = _signed_in("theirs", "director")
        try:
            doc = _intake(client, "Ours", "text", INVESTOR)
            their_meeting = _meeting(other)

            assert _assign(client, their_meeting, doc["id"]).status_code == 404
            assert _material(client, their_meeting).status_code == 404
        finally:
            _cleanup([pid], [ws])
            _cleanup([other_pid], [other_ws])

    def test_unassigning_what_is_not_assigned_is_404(self, restore_client):
        client, pid, ws = _signed_in("unassigned", "director")
        try:
            doc = _intake(client, "Never assigned", "text", INVESTOR)
            meeting = _meeting(client)
            res = client.delete(f"/api/meetings/{meeting}/material/{doc['id']}")
            assert res.status_code == 404
        finally:
            _cleanup([pid], [ws])

    def test_a_low_reader_cannot_strip_material_they_cannot_see(self, restore_client):
        """The DELETE is clearance-gated itself, not merely preceded by a read.

        Otherwise an investor could quietly remove a confidential contract from the
        board's material for a meeting without ever being able to see what they removed —
        a write that acts on data the writer is not cleared for.
        """
        client, pid, ws = _signed_in("strip", "director")
        low, low_pid = _joins(ws, "investor")
        try:
            secret = _intake(client, "Confidential contract", "terms", CONFIDENTIAL)
            meeting = _meeting(client)
            assert _assign(client, meeting, secret["id"]).status_code == 201

            assert low.delete(f"/api/meetings/{meeting}/material/{secret['id']}").status_code == 404
            # Still there for the reader who may see it.
            assert _material(client, meeting).json()["withheld"] == 0
            assert len(_material(client, meeting).json()["documents"]) == 1
        finally:
            _cleanup([pid, low_pid], [ws])


# --- Withholding: the count is the whole disclosure --------------------------


class TestWithholding:
    def test_a_document_above_clearance_is_counted_not_listed(self, restore_client):
        client, pid, ws = _signed_in("withheld", "director")
        low, low_pid = _joins(ws, "investor")
        try:
            public = _intake(client, "Agenda pack", "public text", INVESTOR)
            secret = _intake(client, "Board comp memo", "SECRET_BODY salaries", CONFIDENTIAL)
            meeting = _meeting(client)
            _assign(client, meeting, public["id"])
            _assign(client, meeting, secret["id"])

            res = _material(low, meeting)
            assert res.status_code == 200
            body = res.json()
            assert [d["id"] for d in body["documents"]] == [public["id"]]
            assert body["withheld"] == 1

            # The count is the ONLY thing disclosed. Raw body, so a leak through any
            # field — not just `documents` — fails here.
            raw = res.text
            assert "Board comp memo" not in raw
            assert "SECRET_BODY" not in raw
            assert secret["id"] not in raw
        finally:
            _cleanup([pid, low_pid], [ws])

    def test_material_entirely_above_clearance_reports_the_count_not_an_empty_list(
        self, restore_client
    ):
        """The case a naive implementation gets wrong.

        With every document withheld the filtered query returns no rows, and a count
        derived from those rows is zero — so the meeting reports "no material" to the one
        reader for whom that is most misleading. The count comes from the complement,
        which is why it survives here.
        """
        client, pid, ws = _signed_in("allwithheld", "director")
        low, low_pid = _joins(ws, "investor")
        try:
            meeting = _meeting(client)
            for i in range(3):
                doc = _intake(client, f"Secret {i}", f"body {i}", CONFIDENTIAL)
                _assign(client, meeting, doc["id"])

            body = _material(low, meeting).json()
            assert body["documents"] == []
            assert body["withheld"] == 3
        finally:
            _cleanup([pid, low_pid], [ws])

    def test_an_empty_meeting_is_distinguishable_from_a_fully_withheld_one(self, restore_client):
        """The inversion ADR-018 exists for.

        Both return zero documents. Only the count separates "there is nothing here" from
        "there is something here you may not see", and a director preparing for the
        meeting needs that difference.
        """
        client, pid, ws = _signed_in("distinct", "director")
        low, low_pid = _joins(ws, "investor")
        try:
            empty = _meeting(client, "Nothing filed yet")
            hidden = _meeting(client, "All above your clearance")
            doc = _intake(client, "Secret", "text", CONFIDENTIAL)
            _assign(client, meeting_id := hidden, doc["id"])

            assert _material(low, empty).json() == {"documents": [], "withheld": 0}
            assert _material(low, meeting_id).json() == {"documents": [], "withheld": 1}
        finally:
            _cleanup([pid, low_pid], [ws])

    def test_the_withheld_count_moves_with_the_reader_not_with_the_meeting(self, restore_client):
        """One meeting, two readers, two different true answers."""
        client, pid, ws = _signed_in("perreader", "director")
        low, low_pid = _joins(ws, "investor")
        try:
            meeting = _meeting(client)
            _assign(client, meeting, _intake(client, "Open", "a", INVESTOR)["id"])
            _assign(client, meeting, _intake(client, "Closed", "b", CONFIDENTIAL)["id"])

            assert _material(client, meeting).json()["withheld"] == 0
            assert _material(low, meeting).json()["withheld"] == 1
        finally:
            _cleanup([pid, low_pid], [ws])


# --- Audit -------------------------------------------------------------------


class TestAudit:
    def test_assignment_and_removal_are_audited(self, restore_client):
        client, pid, ws = _signed_in("audit", "director")
        try:
            doc = _intake(client, "Contract", "text", INVESTOR)
            meeting = _meeting(client)
            _assign(client, meeting, doc["id"])
            assert client.delete(f"/api/meetings/{meeting}/material/{doc['id']}").status_code == 200

            rows = _admin_rows(
                "SELECT action, actor_principal_id, payload FROM audit_event "
                "WHERE workspace_id = %s AND aggregate_id = %s AND action IN "
                "('item_added', 'item_removed') ORDER BY created_at",
                (ws, meeting),
            )
            assert [r["action"] for r in rows] == ["item_added", "item_removed"]
            for r in rows:
                payload = r["payload"] if isinstance(r["payload"], dict) else json.loads(r["payload"])
                assert payload["document_id"] == doc["id"]
                # `kind` distinguishes material from a pack item, which shares the action.
                assert payload["kind"] == "material"
                assert str(r["actor_principal_id"]) == pid
        finally:
            _cleanup([pid], [ws])

    def test_a_refused_assignment_writes_no_audit_event(self, restore_client):
        """No event may record something that did not happen (rules.md §2)."""
        client, pid, ws = _signed_in("noaudit", "director")
        low, low_pid = _joins(ws, "investor")
        try:
            secret = _intake(client, "Secret", "text", CONFIDENTIAL)
            meeting = _meeting(client)
            assert _assign(low, meeting, secret["id"]).status_code == 404

            rows = _admin_rows(
                "SELECT action FROM audit_event WHERE workspace_id = %s AND aggregate_id = %s "
                "AND action = 'item_added'",
                (ws, meeting),
            )
            assert rows == []
        finally:
            _cleanup([pid, low_pid], [ws])
