"""Document supersession and the version chain (Meridian P4, ADR-017).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

The chain is a security surface before it is a convenience. A revision may sit above its
predecessor's clearance, so every test that touches a mixed-sensitivity chain asserts
against the **raw response body** rather than against a parsed field — a title leaking
into an unexpected key is exactly the failure a field-by-field assertion would miss.
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

from callosum import llm
from callosum.config import settings
from meridian import documents
from meridian.api import auth, errors
from meridian.api import documents as documents_api

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
    errors.install_exception_handlers(application)
    auth._client = lambda request: _StubClient({"sub": subject, "iss": ISSUER})  # type: ignore[assignment]
    return application


def _workspace(label: str) -> str:
    ws = str(uuid.uuid4())
    _admin("INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s)", (ws, f"{label}-{ws[:6]}", ws))
    return ws


def _principal_with_identity(subject: str, clearance: int) -> str:
    pid = str(uuid.uuid4())
    _admin("INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, 'director', %s)", (pid, f"User {pid[:6]}", clearance))
    _admin("INSERT INTO principal_identity (principal_id, provider, subject) VALUES (%s, %s, %s)", (pid, ISSUER, subject))
    return pid


def _member(principal_id: str, workspace_id: str, clearance: int) -> None:
    _admin(
        "INSERT INTO membership (principal_id, workspace_id, role, clearance, active) VALUES (%s, %s, 'director', %s, true)",
        (principal_id, workspace_id, clearance),
    )


def _cleanup(principal_ids: list[str], workspace_ids: list[str]) -> None:
    for ws in workspace_ids:
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
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


def _signed_in(label: str, clearance: int) -> tuple[TestClient, str, str]:
    subject = f"sub-{uuid.uuid4()}"
    pid = _principal_with_identity(subject, clearance)
    ws = _workspace(label)
    _member(pid, ws, clearance)
    return _client(subject, ws), pid, ws


def _joins(ws: str, clearance: int) -> tuple[TestClient, str]:
    """A second signed-in principal in an EXISTING workspace, at a different clearance.

    Every withholding test needs two readers of one chain. The principal is returned so
    the caller can hand it to the *same* `_cleanup` as the first: a principal who has
    authored a document cannot be deleted before that document is, and
    `document_authored_by_fkey` refuses rather than cascading. Cleaning them separately
    is what the first draft of this file did, and all five two-reader tests failed on it.
    """
    subject = f"sub-{uuid.uuid4()}"
    pid = _principal_with_identity(subject, clearance)
    _member(pid, ws, clearance)
    return _client(subject, ws), pid


def _intake(client: TestClient, title: str, text: str, sensitivity: int) -> dict:
    res = client.post(
        "/api/documents/intake",
        json={"title": title, "doc_type": "memo", "raw_text": text, "sensitivity": sensitivity},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _supersede(client: TestClient, doc_id: str, title: str, text: str, sensitivity: int):
    return client.post(
        f"/api/documents/{doc_id}/supersede",
        json={"title": title, "doc_type": "memo", "raw_text": text, "sensitivity": sensitivity},
    )


# --- The happy path ----------------------------------------------------------


class TestSupersede:
    def test_supersede_links_both_ways_and_increments_the_revision(self, restore_client):
        client, pid, ws = _signed_in("chain", CONFIDENTIAL)
        try:
            v1 = _intake(client, "Q3 forecast", "Revenue is 12M.", INTERNAL)
            assert v1["revision"] == 1
            assert v1["superseded_by_id"] is None

            res = _supersede(client, v1["id"], "Q3 forecast (corrected)", "Revenue is 11.6M.", INTERNAL)
            assert res.status_code == 201, res.text
            v2 = res.json()

            assert v2["revision"] == 2
            assert v2["superseded_by_id"] is None
            assert v2["id"] != v1["id"]

            refetched_v1 = client.get(f"/api/documents/{v1['id']}").json()
            assert refetched_v1["superseded_by_id"] == v2["id"]
            assert refetched_v1["revision"] == 1

    #       The old document keeps its own text and identity. A board that can rewrite
    #       its own record has no record.
            assert refetched_v1["title"] == "Q3 forecast"
        finally:
            _cleanup([pid], [ws])

    def test_the_chain_reports_every_revision_in_order(self, restore_client):
        client, pid, ws = _signed_in("order", CONFIDENTIAL)
        try:
            v1 = _intake(client, "Policy v1", "First statement.", PUBLIC)
            v2 = _supersede(client, v1["id"], "Policy v2", "Second statement.", PUBLIC).json()
            v3 = _supersede(client, v2["id"], "Policy v3", "Third statement.", PUBLIC).json()

            body = client.get(f"/api/documents/{v2['id']}/versions").json()

            assert [r["revision"] for r in body["revisions"]] == [1, 2, 3]
            assert [r["id"] for r in body["revisions"]] == [v1["id"], v2["id"], v3["id"]]
            assert body["withheld"] == 0
            assert body["current_id"] == v3["id"]
        finally:
            _cleanup([pid], [ws])

    def test_the_chain_is_the_same_read_from_any_revision(self, restore_client):
        """Asking from the middle, the head or the tail must answer identically.

        A walk that only went forwards would answer a different history depending on
        where the reader entered it, which is the same defect as a chain that ends at
        the reader's clearance.
        """
        client, pid, ws = _signed_in("anyentry", CONFIDENTIAL)
        try:
            v1 = _intake(client, "A", "one", PUBLIC)
            v2 = _supersede(client, v1["id"], "B", "two", PUBLIC).json()
            v3 = _supersede(client, v2["id"], "C", "three", PUBLIC).json()

            seen = [client.get(f"/api/documents/{d['id']}/versions").json() for d in (v1, v2, v3)]
            assert seen[0] == seen[1] == seen[2]
        finally:
            _cleanup([pid], [ws])

    def test_an_ordinary_document_has_a_chain_of_one(self, restore_client):
        client, pid, ws = _signed_in("single", CONFIDENTIAL)
        try:
            v1 = _intake(client, "Standalone", "Only ever this.", PUBLIC)
            body = client.get(f"/api/documents/{v1['id']}/versions").json()
            assert [r["id"] for r in body["revisions"]] == [v1["id"]]
            assert body["withheld"] == 0
            assert body["current_id"] == v1["id"]
        finally:
            _cleanup([pid], [ws])


# --- Refusals ----------------------------------------------------------------


class TestRefusals:
    def test_a_revision_may_not_lower_sensitivity(self, restore_client):
        """The security core: no silent declassification through a correction."""
        client, pid, ws = _signed_in("downgrade", CONFIDENTIAL)
        try:
            v1 = _intake(client, "Comp review", "Confidential body.", CONFIDENTIAL)
            res = _supersede(client, v1["id"], "Comp review (public)", "Corrected body.", PUBLIC)

            assert res.status_code == 403, res.text
            assert res.json()["error"]["code"] == "forbidden"
            # The detail must be actionable: it names the floor the caller must meet.
            assert "3" in res.json()["error"]["detail"]

            # And nothing was filed. A refused downgrade that still ingested the text
            # would leak it at whatever level the row landed on.
            assert client.get(f"/api/documents/{v1['id']}").json()["superseded_by_id"] is None
            assert len(client.get("/api/documents").json()) == 1
        finally:
            _cleanup([pid], [ws])

    def test_a_revision_may_raise_sensitivity(self, restore_client):
        """The other direction is a legitimate correction — it withdraws access."""
        client, pid, ws = _signed_in("upgrade", CONFIDENTIAL)
        try:
            v1 = _intake(client, "Memo", "Looks harmless.", PUBLIC)
            res = _supersede(client, v1["id"], "Memo (reclassified)", "Actually sensitive.", CONFIDENTIAL)
            assert res.status_code == 201, res.text
            assert res.json()["sensitivity"] == CONFIDENTIAL
        finally:
            _cleanup([pid], [ws])

    def test_a_revision_above_the_callers_clearance_is_refused(self, restore_client):
        """The intake ceiling from #143 still applies — supersede is an intake."""
        client, pid, ws = _signed_in("ceiling", INVESTOR)
        try:
            v1 = _intake(client, "Investor note", "Body.", INVESTOR)
            res = _supersede(client, v1["id"], "Investor note v2", "Corrected.", CONFIDENTIAL)
            assert res.status_code == 403, res.text
            assert "clearance" in res.json()["error"]["detail"].lower()
        finally:
            _cleanup([pid], [ws])

    def test_superseding_twice_is_a_409(self, restore_client):
        client, pid, ws = _signed_in("twice", CONFIDENTIAL)
        try:
            v1 = _intake(client, "Once", "one", PUBLIC)
            assert _supersede(client, v1["id"], "Twice", "two", PUBLIC).status_code == 201
            res = _supersede(client, v1["id"], "Thrice", "three", PUBLIC)

            assert res.status_code == 409, res.text
            assert res.json()["error"]["code"] == "conflict"
        finally:
            _cleanup([pid], [ws])

    def test_the_409_does_not_name_the_successor(self, restore_client):
        """The successor may sit above the caller's clearance.

        A chain's sensitivity may rise, so the document that replaced one you can read
        is not necessarily one you can read. An id in an error message is a disclosure
        the read paths would have refused.
        """
        client, pid, ws = _signed_in("noname", CONFIDENTIAL)
        try:
            v1 = _intake(client, "Base", "base text", PUBLIC)
            v2 = _supersede(client, v1["id"], "Secret revision", "secret text", CONFIDENTIAL).json()
            res = _supersede(client, v1["id"], "Another", "another", PUBLIC)

            assert res.status_code == 409
            raw = res.text
            assert v2["id"] not in raw
            assert "Secret revision" not in raw
        finally:
            _cleanup([pid], [ws])

    def test_superseding_a_document_above_clearance_is_404_not_403(self, restore_client):
        """The existence oracle stays closed on the write path too."""
        low, low_pid, ws = _signed_in("oracle", INVESTOR)
        # Outside the try: if this raised, `high_pid` would be unbound in the finally
        # and a NameError would replace whatever actually went wrong.
        high, high_pid = _joins(ws, CONFIDENTIAL)
        try:
            secret = _intake(high, "Termination terms", "Confidential.", CONFIDENTIAL)
            res = _supersede(low, secret["id"], "Revision", "text", INVESTOR)

            assert res.status_code == 404, res.text
            assert "Termination" not in res.text
        finally:
            _cleanup([low_pid, high_pid], [ws])

    def test_a_document_in_another_workspace_cannot_be_superseded(self, restore_client):
        alice, alice_pid, ws_a = _signed_in("tenant-a", CONFIDENTIAL)
        bob, bob_pid, ws_b = _signed_in("tenant-b", CONFIDENTIAL)
        try:
            theirs = _intake(bob, "Their document", "Their text.", PUBLIC)
            res = _supersede(alice, theirs["id"], "Mine now", "my text", PUBLIC)

            assert res.status_code == 404, res.text
            assert "Their document" not in res.text
            # And their document is untouched.
            assert bob.get(f"/api/documents/{theirs['id']}").json()["superseded_by_id"] is None
        finally:
            _cleanup([alice_pid], [ws_a])
            _cleanup([bob_pid], [ws_b])

    def test_a_duplicate_revision_is_still_a_duplicate(self, restore_client):
        """Supersede routes through intake, so dedup still applies to the new text."""
        client, pid, ws = _signed_in("dupe", CONFIDENTIAL)
        try:
            v1 = _intake(client, "Original", "identical text", PUBLIC)
            res = _supersede(client, v1["id"], "Revision", "identical text", PUBLIC)

            assert res.status_code == 409, res.text
            assert client.get(f"/api/documents/{v1['id']}").json()["superseded_by_id"] is None
        finally:
            _cleanup([pid], [ws])


# --- Withholding -------------------------------------------------------------


class TestWithholding:
    def test_a_withheld_revision_is_a_count_and_nothing_else(self, restore_client):
        """Asserted against the RAW body, so a leak into any field fails."""
        low, low_pid, ws = _signed_in("withheld", INVESTOR)
        # Outside the try: if this raised, `high_pid` would be unbound in the finally
        # and a NameError would replace whatever actually went wrong.
        high, high_pid = _joins(ws, CONFIDENTIAL)
        try:
            v1 = _intake(high, "Vendor terms", "Public draft.", INVESTOR)
            v2 = _supersede(high, v1["id"], "Project Halberd termination terms", "Confidential correction.", CONFIDENTIAL).json()

            body = low.get(f"/api/documents/{v1['id']}/versions")
            assert body.status_code == 200, body.text
            raw = body.text
            parsed = body.json()

            assert parsed["withheld"] == 1
            assert [r["id"] for r in parsed["revisions"]] == [v1["id"]]

            for secret in ("Halberd", "termination", "Termination", v2["id"]):
                assert secret not in raw, f"{secret!r} leaked into the chain response"
        finally:
            _cleanup([low_pid, high_pid], [ws])

    def test_the_successor_pointer_is_redacted_on_the_list_and_get_paths_too(self, restore_client):
        """The same rule, on the surfaces that do not go through `version_chain`.

        `superseded_by_id` is on every document read, not only the chain, so
        `list_documents` and `get_document` leak the same id if they do not redact it —
        and they resolve it in SQL while the chain resolves it in Python. Two
        implementations of one rule need two guards, or the day they diverge is the day
        nobody notices.

        The id matters more than it looks: `_document_id` is
        `uuid5(_INTAKE_NAMESPACE, f"{workspace_id}:{content_hash}")` over a public
        namespace constant, so an id is a value a holder of candidate plaintext can
        derive and compare. Returning one for a document above the caller's clearance is
        a content-confirmation oracle, not an unusable handle.
        """
        low, low_pid, ws = _signed_in("redact", INVESTOR)
        high, high_pid = _joins(ws, CONFIDENTIAL)
        try:
            v1 = _intake(high, "Vendor terms", "Public draft.", INVESTOR)
            v2 = _supersede(high, v1["id"], "Sealed correction", "Confidential.", CONFIDENTIAL).json()

            listed = low.get("/api/documents")
            fetched = low.get(f"/api/documents/{v1['id']}")

            assert [d["id"] for d in listed.json()] == [v1["id"]]
            assert listed.json()[0]["superseded_by_id"] is None
            assert fetched.json()["superseded_by_id"] is None

            for raw in (listed.text, fetched.text):
                assert v2["id"] not in raw
                assert "Sealed" not in raw

            # The cleared reader still sees the link — redaction is per-caller, not a
            # blanket removal that would make the feature useless for the people it is for.
            assert high.get(f"/api/documents/{v1['id']}").json()["superseded_by_id"] == v2["id"]
        finally:
            _cleanup([low_pid, high_pid], [ws])

    def test_current_id_is_null_when_the_current_revision_is_withheld(self, restore_client):
        """Never fall back to the newest READABLE revision.

        That fallback would mark a superseded document as current — worse than saying
        nothing, because the reader acts on a corrected document with no signal.
        """
        low, low_pid, ws = _signed_in("nocurrent", INVESTOR)
        # Outside the try: if this raised, `high_pid` would be unbound in the finally
        # and a NameError would replace whatever actually went wrong.
        high, high_pid = _joins(ws, CONFIDENTIAL)
        try:
            v1 = _intake(high, "Open figure", "12M.", INVESTOR)
            _supersede(high, v1["id"], "Corrected figure", "11.6M.", CONFIDENTIAL)

            parsed = low.get(f"/api/documents/{v1['id']}/versions").json()
            assert parsed["current_id"] is None
            assert parsed["withheld"] == 1
        finally:
            _cleanup([low_pid, high_pid], [ws])

    def test_the_chain_of_a_document_above_clearance_is_404(self, restore_client):
        """A chain read must not be a way around `get_document`'s clearance gate."""
        low, low_pid, ws = _signed_in("chain404", INVESTOR)
        # Outside the try: if this raised, `high_pid` would be unbound in the finally
        # and a NameError would replace whatever actually went wrong.
        high, high_pid = _joins(ws, CONFIDENTIAL)
        try:
            secret = _intake(high, "Sealed", "Confidential.", CONFIDENTIAL)
            res = low.get(f"/api/documents/{secret['id']}/versions")

            assert res.status_code == 404, res.text
            assert "Sealed" not in res.text
        finally:
            _cleanup([low_pid, high_pid], [ws])

    def test_readable_revisions_are_a_prefix_so_the_numbering_has_no_gaps(self, restore_client):
        """Pins the property `version_chain`'s docstring derives.

        Because a revision may never lower sensitivity, a chain's sensitivities are
        monotonically non-decreasing — so what a caller can read is always a PREFIX and
        what is withheld is always a SUFFIX. The visible revision numbers therefore have
        no gaps and disclose no position.

        This is a consequence of the downgrade refusal, not an assumption in the walk. If
        that rule is ever relaxed, this test fails and the disclosure question is reopened
        deliberately instead of changing underneath the code.
        """
        low, low_pid, ws = _signed_in("prefix", INVESTOR)
        # Outside the try: if this raised, `high_pid` would be unbound in the finally
        # and a NameError would replace whatever actually went wrong.
        high, high_pid = _joins(ws, CONFIDENTIAL)
        try:
            v1 = _intake(high, "R1", "one", PUBLIC)
            v2 = _supersede(high, v1["id"], "R2", "two", INVESTOR).json()
            v3 = _supersede(high, v2["id"], "R3", "three", CONFIDENTIAL).json()
            _supersede(high, v3["id"], "R4", "four", CONFIDENTIAL)

            parsed = low.get(f"/api/documents/{v1['id']}/versions").json()
            visible = [r["revision"] for r in parsed["revisions"]]

            assert visible == [1, 2], visible
            assert visible == list(range(1, len(visible) + 1)), "a gap appeared in the visible revisions"
            assert parsed["withheld"] == 2
            assert parsed["current_id"] is None
        finally:
            _cleanup([low_pid, high_pid], [ws])


# --- Audit -------------------------------------------------------------------


class TestAudit:
    def test_supersession_records_both_sensitivities(self, restore_client):
        client, pid, ws = _signed_in("audit", CONFIDENTIAL)
        try:
            v1 = _intake(client, "Before", "before text", INVESTOR)
            v2 = _supersede(client, v1["id"], "After", "after text", INTERNAL).json()

            rows = _admin_rows(
                "SELECT actor_principal_id, aggregate_id, payload FROM audit_event "
                "WHERE workspace_id = %s AND action = 'superseded' AND aggregate_type = 'document'",
                (uuid.UUID(ws),),
            )
            assert len(rows) == 1, rows
            event = rows[0]
            payload = event["payload"] if isinstance(event["payload"], dict) else json.loads(event["payload"])

            assert str(event["actor_principal_id"]) == pid
            assert str(event["aggregate_id"]) == v1["id"]
            assert payload["old_document_id"] == v1["id"]
            assert payload["new_document_id"] == v2["id"]
            assert payload["revision"] == 2
            # Both levels, so "was anything declassified?" is answerable from the trail
            # alone rather than by joining back to rows that may have moved since.
            assert payload["old_sensitivity"] == INVESTOR
            assert payload["new_sensitivity"] == INTERNAL
        finally:
            _cleanup([pid], [ws])

    def test_a_refused_supersession_records_no_event(self, restore_client):
        client, pid, ws = _signed_in("norecord", CONFIDENTIAL)
        try:
            v1 = _intake(client, "Sealed", "sealed text", CONFIDENTIAL)
            assert _supersede(client, v1["id"], "Leak", "leak text", PUBLIC).status_code == 403

            rows = _admin_rows(
                "SELECT id FROM audit_event WHERE workspace_id = %s AND action = 'superseded'",
                (uuid.UUID(ws),),
            )
            assert rows == [], "an event was recorded for something that did not happen"
        finally:
            _cleanup([pid], [ws])


# --- The walk ----------------------------------------------------------------


class TestChainWalk:
    def test_the_walk_is_bounded(self, restore_client):
        """A cycle must refuse, not hang.

        Cycles are unreachable through `supersede_document`, which always creates its
        successor. This builds one behind the domain's back — the shape a future caller
        that supersedes with an *existing* document would produce — and asserts the read
        refuses rather than holding a connection until something else times out.
        """
        client, pid, ws = _signed_in("cycle", CONFIDENTIAL)
        try:
            a = _intake(client, "A", "a text", PUBLIC)
            b = _supersede(client, a["id"], "B", "b text", PUBLIC).json()
            # Close the loop directly. `document_no_self_supersede` forbids the one-step
            # case, so this is the smallest cycle the schema permits.
            _admin(
                "UPDATE document SET superseded_by_id = %s WHERE id = %s",
                (uuid.UUID(a["id"]), uuid.UUID(b["id"])),
            )

            with pytest.raises(documents.DocumentError, match="exceeds"):
                documents.version_chain(a["id"], workspace_id=ws, clearance=CONFIDENTIAL)
        finally:
            _cleanup([pid], [ws])
