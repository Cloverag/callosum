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
import json
import os
import uuid

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip("set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests", allow_module_level=True)

from callosum import identity, llm
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


def _admin_fetch(sql: str, params: tuple = ()) -> list:
    from psycopg.rows import dict_row
    with psycopg.connect(settings().postgres_dsn, row_factory=dict_row) as conn:
        return conn.execute(sql, params).fetchall()


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


def _product_routers():
    """Every router the product exposes, discovered rather than listed.

    The sweep walks `app.openapi()`, so the schema it sees is only as complete as the
    app it builds — and this function used to be a hand-written list of three routers.
    That is the same defect the walk exists to avoid, one level up: a new router would
    join the product and never join the sweep, and every assertion here would keep
    passing while covering less. Enumerated from the package so it cannot drift.
    """
    import importlib
    import pkgutil

    from meridian import api as api_pkg

    found = []
    for info in pkgutil.iter_modules(api_pkg.__path__):
        module = importlib.import_module(f"meridian.api.{info.name}")
        router = getattr(module, "router", None)
        if router is not None and info.name != "auth":
            found.append(router)
    return found


def _app(subject: str) -> FastAPI:
    application = FastAPI()
    application.add_middleware(SessionMiddleware, secret_key="test-secret-not-for-use")
    application.include_router(auth.router)
    for router in _product_routers():
        application.include_router(router)
    errors.install_exception_handlers(application)
    auth._client = lambda request: _StubClient({"sub": subject, "iss": ISSUER})  # type: ignore[assignment]
    return application


def _signed_in(ws: str, role: str) -> TestClient:
    """`role`, not `clearance` (#166): the caller's effective clearance is derived
    from `membership.role` at read time, so hardcoding `role='director'` here while
    varying only the stored `clearance` argument — the original shape of this
    helper — silently gave every caller `director`'s mapped clearance (3)
    regardless of what was requested. Confirmed the hard way: with `CONFIDENTIAL`
    also `== 3`, the "low" (`INVESTOR`-requesting) reader in this file's `scene`
    fixture was actually granted director-level access, and the sweep caught it —
    see the report this was found and fixed in.
    """
    subject = f"sub-{uuid.uuid4()}"
    pid = str(uuid.uuid4())
    clearance = identity.ROLE_TO_CLEARANCE[role]
    _admin("INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, %s, %s)", (pid, f"U {pid[:6]}", role, clearance))
    _admin("INSERT INTO principal_identity (principal_id, provider, subject) VALUES (%s, %s, %s)", (pid, ISSUER, subject))
    _admin(
        "INSERT INTO membership (principal_id, workspace_id, role, clearance, active) VALUES (%s, %s, %s, %s, true)",
        (pid, ws, role, clearance),
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

    # 'director' maps to clearance 3, exactly CONFIDENTIAL; 'investor' maps to 1,
    # exactly INVESTOR — the roles are chosen to reproduce the same numeric levels
    # this fixture named before #166, not picked arbitrarily.
    high, high_pid = _signed_in(ws, "director")
    low, low_pid = _signed_in(ws, "investor")

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

    # A meeting holding BOTH documents as material. Without it the material routes are
    # reachable in the schema but answer 404 for want of a real meeting, which would
    # sweep the shape of the endpoint rather than the endpoint.
    meeting = high.post("/api/meetings", json={"title": "Sweep meeting"})
    assert meeting.status_code == 201, meeting.text
    meeting_id = meeting.json()["id"]
    for doc_id in (secret_doc["id"], public_doc["id"]):
        assigned = high.post(f"/api/meetings/{meeting_id}/material", json={"document_id": doc_id})
        assert assigned.status_code == 201, assigned.text

    yield {
        "ws": ws, "low": low, "high": high, "meeting": meeting_id,
        "secret": secret_doc, "public": public_doc, "revision": revision.json(),
    }

    # A route this sweep reaches can have a side effect this fixture never asked
    # for. POST /workspaces (#166 step 5) is exactly that: it depends on
    # CurrentSession only (no membership required to call it — that is the whole
    # point of the route), takes one required string body that _example()
    # synthesises, and SUCCEEDS when the write sweep calls it as `low`. No leak —
    # the response is `{"workspace_id": ...}` and nothing echoes the name back —
    # but it is a REAL workspace, with `low_pid` as its founder, that this
    # fixture's `ws` was never told about. Found by clover-38 reviewing the route,
    # not by the sweep failing: every assertion still passes, and without this the
    # database is left worse by one zero-membership workspace per sweep run —
    # exactly the state `test_workspace_bootstrap.py::
    # test_a_workspace_without_its_founder_membership_makes_its_creator_unresolvable`
    # calls unusable, and it would accumulate forever (same class as #177).
    #
    # Discovered generically — by asking what OTHER workspaces `high_pid`/`low_pid`
    # ended up in, rather than by naming this one route — so a DIFFERENT future
    # route with the same kind of side effect is caught by this fixture without
    # anyone having to remember to extend it, the same reason `_reachable_writes`
    # itself walks the schema instead of a hand-written list.
    extra_workspace_ids = [
        r["workspace_id"] for r in _admin_fetch(
            "SELECT DISTINCT workspace_id FROM membership WHERE principal_id IN (%s, %s) AND workspace_id != %s",
            (high_pid, low_pid, ws),
        )
    ]
    for extra in extra_workspace_ids:
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (extra,))
        _admin("DELETE FROM membership WHERE workspace_id = %s", (extra,))
        _admin("DELETE FROM workspace WHERE id = %s", (extra,))

    _admin("DELETE FROM meeting_document WHERE workspace_id = %s", (ws,))
    _admin("DELETE FROM meeting WHERE workspace_id = %s", (ws,))
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


def _fill(path: str, scene) -> list[str]:
    """Every substitution of a templated path from the ids under test."""
    if "{" not in path:
        return [path]
    ids = (scene["secret"]["id"], scene["public"]["id"], scene["revision"]["id"])
    out = []
    for ident in ids:
        u = (path.replace("{document_id}", ident).replace("{pack_id}", ident)
                 .replace("{meeting_id}", scene["meeting"]).replace("{minutes_id}", ident)
                 .replace("{decision_id}", ident).replace("{resolution_id}", ident)
                 .replace("{commitment_id}", ident).replace("{agenda_item_id}", ident)
                 .replace("{member_id}", ident).replace("{board_member_id}", ident)
                 .replace("{conflict_id}", ident).replace("{pack_item_id}", ident))
        if "{" not in u:
            out.append(u)
    return out


def _example(schema: dict, spec: dict, scene, depth: int = 0):
    """A minimal value satisfying a JSON schema, resolving $ref against the spec.

    Synthesised from the schema rather than hand-written per endpoint, for the reason
    the GET walk is schema-driven: a body hand-written here would go stale the moment a
    field is added, and the endpoint would quietly start failing validation instead of
    reaching the domain — passing the sweep by never getting far enough to leak.
    """
    if depth > 4:
        return None
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        return _example(spec["components"]["schemas"].get(name, {}), spec, scene, depth + 1)
    for key in ("anyOf", "oneOf", "allOf"):
        if key in schema:
            return _example(schema[key][0], spec, scene, depth + 1)
    kind = schema.get("type")
    if kind == "object":
        props = schema.get("properties", {})
        return {
            name: _example(sub, spec, scene, depth + 1)
            for name, sub in props.items()
            if name in schema.get("required", list(props))
        }
    if kind == "array":
        return []
    if kind == "integer":
        return 1
    if kind == "number":
        return 1.0
    if kind == "boolean":
        return True
    if schema.get("format") == "uuid":
        return scene["secret"]["id"]
    if "enum" in schema:
        return schema["enum"][0]
    # A string with no format. The confidential document id is the most useful value a
    # sweep can put here: if an endpoint echoes an id it was handed back into a field it
    # should not, that is the same disclosure as inventing one.
    return scene["secret"]["id"]


def _reachable_writes(scene) -> list[tuple[str, str, object]]:
    """Every POST / PATCH / DELETE in the schema, as (method, url, body).

    `test_no_get_endpoint_leaks_confidential_material` walked `get` only, and that was
    the defect: the richest domain errors in this product are on writes.
    `supersede_document` alone raises four, and `assign_material` answers 404 for a
    document the caller may not read — an answer whose whole job is to say nothing, and
    which nothing was checking.

    Bodies are synthesised from `requestBody`, so an endpoint that gains a required
    field stays reachable instead of silently falling back to a 422 that never touches
    the domain.
    """
    spec = scene["low"].app.openapi()
    calls: list[tuple[str, str, object]] = []
    for path, item in spec["paths"].items():
        if path.startswith("/auth"):
            continue
        for method in ("post", "patch", "delete"):
            op = item.get(method)
            if op is None:
                continue
            body = None
            content = (op.get("requestBody") or {}).get("content", {})
            if "application/json" in content:
                body = _example(content["application/json"].get("schema", {}), spec, scene)
            for url in _fill(path, scene):
                calls.append((method, url, body))
    return sorted(set((m, u, json.dumps(b, sort_keys=True)) for m, u, b in calls))


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


def test_no_write_endpoint_leaks_confidential_material(scene):
    """The other half of the surface, and the half that was never swept.

    A write refuses more often than a read succeeds, and a refusal is where a message
    gets written by hand — `errors.py:170` passes any domain exception's `str()` to the
    client unless it has a fixed detail. So the strings most likely to name something
    are on exactly the paths `_reachable_gets` could not see.

    Bodies are synthesised, so some calls answer 422 without reaching the domain. Those
    are swept anyway and cost nothing: a validation error that echoes a confidential id
    back is the same leak arriving through a different door.
    """
    leaks: list[str] = []
    reached = 0

    for method, url, raw in _reachable_writes(scene):
        body = json.loads(raw)
        response = getattr(scene["low"], method)(url, json=body) if body is not None else getattr(scene["low"], method)(url)
        reached += 1
        text = response.text
        for label, needle in _needles(scene).items():
            # An id the caller put IN the request is not a disclosure coming back out.
            if needle in url or (body is not None and needle in raw):
                continue
            if needle in text:
                leaks.append(f"{method.upper()} {url} ({response.status_code}) leaked {label}")

    assert reached >= 20, f"the write sweep reached only {reached} operations; it is not testing what it claims"
    assert leaks == [], "P4 exit criterion violated on a write path:\n  " + "\n  ".join(leaks)


def test_the_write_sweep_reaches_the_endpoints_that_refuse_hardest(scene):
    """A sweep that never gets past validation proves nothing about the domain.

    Pinned by name because these three are the reason the write sweep exists: each
    raises a domain error whose message is written by hand and returned verbatim.
    Synthesised bodies drift when a schema changes, and the failure is silent — every
    call 422s, the sweep stays green, and the domain is never reached.
    """
    urls = {f"{m.upper()} {u}" for m, u, _ in _reachable_writes(scene)}
    secret = scene["secret"]["id"]
    meeting = scene["meeting"]
    assert f"POST /api/documents/{secret}/supersede" in urls
    assert f"POST /api/meetings/{meeting}/material" in urls
    assert f"DELETE /api/meetings/{meeting}/material/{secret}" in urls


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
