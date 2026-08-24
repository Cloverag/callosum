"""P4 exit-criterion sweep: restricted material must not reach a lower clearance.

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

---------------------------------------------------------------------------
WHY THIS IS A SWEEP AND NOT A LIST OF TESTS
---------------------------------------------------------------------------
P4's exit criterion is "restricted titles, text, quotes, graph facts, and hints cannot
leak". Every per-endpoint test written against it proves one endpoint. None of them says
anything about the endpoint somebody adds next month, and the failure mode is silent —
a new route is registered, it returns a document field nobody classified, and every
existing test still passes.

That is the shape of the defect this session already produced once. `superseded_by_id`
was added to the document response for good reasons; it leaked the id of a *withheld*
revision, and it did so on three surfaces at once. No amount of adding endpoints to a
hand-written list would have caught it, because the field was new.

So this file does not name endpoints. It **walks the OpenAPI schema**, calls every
document-bearing operation it can reach as a low-clearance caller, and asserts that
nothing identifying a confidential document appears anywhere in the raw response bytes.
A new route joins the sweep by existing.

---------------------------------------------------------------------------
WHY THE ID IS A NEEDLE, NOT JUST THE TITLE
---------------------------------------------------------------------------
Document ids are not opaque. `meridian.documents._document_id` is

    uuid5(_INTAKE_NAMESPACE, f"{workspace_id}:{content_hash}")

over a namespace constant that is public in the source. Anyone holding candidate
plaintext derives the id and compares. An id for a document above the caller's clearance
is therefore a content-confirmation oracle, which is the P4 criterion's word "hints"
doing real work rather than being decorative.
"""

from __future__ import annotations

import hashlib
import os
import uuid

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip("set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests", allow_module_level=True)

from callosum import llm
from callosum.config import settings
from meridian.api import auth, errors
from meridian.api import documents as documents_api
from meridian.api import packs as packs_api

pytestmark = pytest.mark.integration

ISSUER = "https://keycloak.example/realms/meridian"
INVESTOR = 1
CONFIDENTIAL = 3

#: Strings that must not appear in any low-clearance response body. Chosen to be
#: unmistakable: a false positive from an unrelated word would be worse than useless,
#: and a substring that could occur naturally would make the sweep untrustworthy.
SECRET_TITLE = "ZZQX-Halberd-Termination-Terms"
SECRET_BODY = "ZZQX the acquisition price is 41.5M and Rao dissented"


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
    def _deterministic_embed(texts: list[str], input_type: str = "document") -> list[list[float]]:
        out = []
        for t in texts:
            seed = int(hashlib.md5(t.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
            out.append([0.001 * ((i + int(seed * 100)) % 10 + 1) for i in range(1024)])
        return out

    monkeypatch.setattr(llm, "embed", _deterministic_embed)


@pytest.fixture(autouse=True)
def stub_extraction(monkeypatch):
    from callosum import extract
    from callosum.ontology import FailureReason, RelationType

    def _fake_extract(chunk_text: str):
        quote = chunk_text[: min(40, len(chunk_text))]
        rel = extract.Relationship(
            source="Test Source", type=RelationType.PROPOSED, target="Test Target",
            evidence=quote, confidence=0.9,
        )
        # The quote is a verbatim span of the source, so a quarantine row carries the
        # document's sensitivity. This failure is what puts SECRET_BODY into the
        # quarantine table, which is one of the surfaces being swept.
        failure = extract.Failure(
            source="Bad Source", relation="PROPOSED", target="Bad Target",
            quote=chunk_text[:60], confidence=0.5,
            reason=FailureReason.QUOTE_NOT_FOUND, detail="stubbed failure",
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
    application.include_router(packs_api.router)
    errors.install_exception_handlers(application)
    auth._client = lambda request: _StubClient({"sub": subject, "iss": ISSUER})  # type: ignore[assignment]
    return application


def _signed_in(ws: str, clearance: int) -> TestClient:
    subject = f"sub-{uuid.uuid4()}"
    pid = str(uuid.uuid4())
    _admin("INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, 'director', %s)", (pid, f"U {pid[:6]}", clearance))
    _admin("INSERT INTO principal_identity (principal_id, provider, subject) VALUES (%s, %s, %s)", (pid, ISSUER, subject))
    _admin(
        "INSERT INTO membership (principal_id, workspace_id, role, clearance, active) VALUES (%s, %s, 'director', %s, true)",
        (pid, ws, clearance),
    )
    client = TestClient(_app(subject), follow_redirects=False)
    assert client.get("/auth/callback").status_code == 303
    assert client.post("/auth/workspace", json={"workspace_id": ws}).status_code == 200
    return client, pid


@pytest.fixture
def scene(restore_client):
    """One workspace holding a confidential document and a public one.

    The confidential document is created through **real intake**, not an INSERT, so its
    chunks, its derived id and its quarantine rows all exist exactly as they would in
    production. A hand-inserted row would not populate the surfaces this sweeps.
    """
    ws = str(uuid.uuid4())
    _admin("INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s)", (ws, f"sweep-{ws[:6]}", ws))

    high, high_pid = _signed_in(ws, CONFIDENTIAL)
    low, low_pid = _signed_in(ws, INVESTOR)

    secret = high.post("/api/documents/intake", json={
        "title": SECRET_TITLE, "doc_type": "memo", "raw_text": SECRET_BODY, "sensitivity": CONFIDENTIAL,
    })
    assert secret.status_code == 201, secret.text
    secret_doc = secret.json()

    public = high.post("/api/documents/intake", json={
        "title": "Quarterly update", "doc_type": "memo",
        "raw_text": "Ordinary text that anyone may read.", "sensitivity": INVESTOR,
    })
    assert public.status_code == 201, public.text
    public_doc = public.json()

    # A revision ABOVE the public document, so the withheld-successor path is in scope.
    revision = high.post(f"/api/documents/{public_doc['id']}/supersede", json={
        "title": f"{SECRET_TITLE}-revision", "doc_type": "memo",
        "raw_text": f"{SECRET_BODY} (revised)", "sensitivity": CONFIDENTIAL,
    })
    assert revision.status_code == 201, revision.text

    yield {
        "ws": ws, "low": low, "high": high,
        "secret": secret_doc, "public": public_doc, "revision": revision.json(),
    }

    _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
    _admin("DELETE FROM extraction_failure WHERE workspace_id = %s", (ws,))
    _admin("DELETE FROM proposed_change WHERE workspace_id = %s", (ws,))
    _admin("DELETE FROM chunk WHERE workspace_id = %s", (ws,))
    _admin("UPDATE document SET superseded_by_id = NULL WHERE workspace_id = %s", (ws,))
    _admin("DELETE FROM document WHERE workspace_id = %s", (ws,))
    _admin("DELETE FROM membership WHERE workspace_id = %s", (ws,))
    for pid in (high_pid, low_pid):
        _admin("DELETE FROM principal WHERE id = %s", (pid,))
    _admin("DELETE FROM workspace WHERE id = %s", (ws,))


def _reachable_gets(scene) -> list[str]:
    """Every GET in the schema, with path parameters filled from the scene.

    Enumerated from `app.openapi()` rather than from a hand-written list — the whole
    point is that a route added later joins this sweep without anyone remembering to add
    it here. Paths whose parameters cannot be filled from the scene are returned too,
    substituted with the ids under test, because "does this leak" is exactly the question
    for an id the caller is not supposed to resolve.
    """
    spec = scene["low"].app.openapi()
    urls: list[str] = []
    for path, item in spec["paths"].items():
        if "get" not in item or path.startswith("/auth"):
            continue
        if "{" not in path:
            urls.append(path)
            continue
        for ident in (scene["secret"]["id"], scene["public"]["id"], scene["revision"]["id"]):
            urls.append(
                path.replace("{document_id}", ident).replace("{pack_id}", ident).replace("{meeting_id}", ident)
            )
    return sorted(set(urls))


def _needles(scene) -> dict[str, str]:
    """What must never appear, and the name of the leak each one would be."""
    return {
        "the confidential title": SECRET_TITLE,
        "the confidential body text": SECRET_BODY,
        "the confidential document id": scene["secret"]["id"],
        "the withheld revision id": scene["revision"]["id"],
    }


def test_no_get_endpoint_leaks_confidential_material(scene):
    """The sweep. Every reachable GET, read as a low-clearance caller.

    ---------------------------------------------------------------------------
    AN ID THE CALLER SUPPLIED IS NOT A DISCLOSURE
    ---------------------------------------------------------------------------
    `GET /api/documents/{id}` for a document above clearance answers 404 with that id in
    the detail — `DocumentNotFound(str(document_id))`. The first run of this sweep
    flagged six of those as leaks. They are not: the caller typed the id into the URL,
    so the response tells them nothing they did not already hold, and the 404 is the
    correct fail-closed answer (it is deliberately indistinguishable from "no such
    document", so it is not an existence oracle either).

    A needle found in the URL is therefore skipped for that request and only that
    request. The exclusion is per-URL rather than global on purpose: the same id
    appearing in a response to a DIFFERENT url — a list, a chain, a pack — is exactly
    the disclosure this sweep exists to catch, and a global skip would blind it.
    """
    leaks: list[str] = []
    checked = 0

    for url in _reachable_gets(scene):
        response = scene["low"].get(url)
        # A 404 or a 422 is a correct answer, and its BODY is still swept — an error
        # message that names something the caller did NOT ask about is the classic
        # version of this leak.
        checked += 1
        body = response.text
        for label, needle in _needles(scene).items():
            if needle in url:
                continue
            if needle in body:
                leaks.append(f"{url} ({response.status_code}) leaked {label}")

    assert checked >= 4, f"the sweep reached only {checked} endpoints; it is not testing what it claims"
    assert leaks == [], "P4 exit criterion violated:\n  " + "\n  ".join(leaks)


def test_the_sweep_would_fail_if_something_leaked(scene):
    """Guard the guard.

    A sweep that passes because its needles never appear ANYWHERE — including in
    responses that should contain them — is a test that cannot fail. This asserts the
    cleared reader DOES see the material, so the negative result above means "filtered"
    rather than "the fixture never created anything".
    """
    body = scene["high"].get("/api/documents").text
    assert SECRET_TITLE in body, "the fixture never created the confidential document"

    chain = scene["high"].get(f"/api/documents/{scene['public']['id']}/versions").text
    assert scene["revision"]["id"] in chain, "the fixture never created the withheld revision"


def test_the_low_reader_still_sees_what_they_are_entitled_to(scene):
    """Fail-closed must not mean fail-empty.

    A filter that returned nothing to anyone would pass the sweep and destroy the
    product. The investor-clearance reader must still get their own document.
    """
    body = scene["low"].get("/api/documents").json()
    titles = [d["title"] for d in body]
    assert "Quarterly update" in titles
    assert SECRET_TITLE not in titles


def test_quarantine_rows_from_a_confidential_document_are_filtered(scene):
    """Named separately because it is the surface that shipped this defect once.

    `list_quarantine` took no clearance argument at all before #128's review: a
    quarantine row carries a verbatim quote, a proposed graph fact and a document id, so
    it was readable at any clearance in the workspace. The sweep covers it generically;
    this states the case so a regression reads as what it is.
    """
    rows = scene["low"].get("/api/documents/quarantine").json()
    assert all(SECRET_BODY not in r["quote"] for r in rows)
    assert all(r["document_id"] != scene["secret"]["id"] for r in rows)

    cleared = scene["high"].get("/api/documents/quarantine").json()
    assert any(r["document_id"] == scene["secret"]["id"] for r in cleared), (
        "the confidential document produced no quarantine rows, so the assertion above "
        "proved nothing"
    )
