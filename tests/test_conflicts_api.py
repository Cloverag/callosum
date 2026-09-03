"""The entity-conflict review endpoints (Meridian, H-15).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.

Same harness as `test_decisions_api.py`. It exists because the coverage this
router had was one assertion:

    def test_conflicts_api_router_registered():
        paths = main.app.openapi()["paths"]
        assert any("/api/conflicts" in p for p in paths)

A route appearing in the OpenAPI document proves that a decorator ran at import
time. It does not call the handler, so it cannot see anything the handler does —
and both handlers that do work called a name that has never existed:

    conflicts.py:43   deps.resolve_principal(...)   # deps exports resolve_principal_by_id
    conflicts.py:81   store.connect_neo4j()         # store exports neo()

Every `GET /api/conflicts` raised `AttributeError` and returned 500, and every
approval would have done the same before touching Neo4j. The full gated suite was
green throughout — 631 passed — because nothing in it made the call.

So these tests assert status codes and bodies from the real handlers, against the
real database. The rule they enforce is that a registration assertion is not
coverage: an endpoint is tested when something has asked it for an answer.
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
from meridian.api import auth, errors
from meridian.api import conflicts as conflicts_api

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
    application.include_router(conflicts_api.router)
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


def _member(principal_id: str, workspace_id: str, role: str = "advisor", active: bool = True) -> None:
    """`role`, not `clearance` (#166): effective clearance is derived from
    `membership.role` at read time. Default `'advisor'` matches this file's old
    default (`clearance=2`).
    """
    _admin(
        "INSERT INTO membership (principal_id, workspace_id, role, clearance, active)"
        " VALUES (%s, %s, %s, %s, %s)",
        (principal_id, workspace_id, role, identity.ROLE_TO_CLEARANCE[role], active),
    )


def _seed_conflict(
    workspace_id: str,
    *,
    name_a: str = "Acme Holdings",
    name_b: str = "ACME Holdings Ltd",
    similarity: float = 0.94,
    sensitivity: int = 1,
    status: str = "pending",
) -> str:
    cid = str(uuid.uuid4())
    _admin(
        """
        INSERT INTO entity_conflict
               (id, workspace_id, name_a, type_a, name_b, type_b,
                similarity, quote_a, quote_b, sensitivity, status)
        VALUES (%s, %s, %s, 'org', %s, 'org', %s, %s, %s, %s, %s)
        """,
        (
            cid,
            workspace_id,
            name_a,
            name_b,
            similarity,
            f"...as agreed with {name_a} in Q3...",
            f"...the {name_b} contract renews...",
            sensitivity,
            status,
        ),
    )
    return cid


def _cleanup(principal_ids: list[str], workspace_ids: list[str]) -> None:
    for ws in workspace_ids:
        _admin("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM entity_conflict WHERE workspace_id = %s", (ws,))
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


class TestListing:
    def test_lists_pending_conflicts(self, restore_client):
        """The assertion the registration test could not make: a 200 with a body."""
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("conflicts")
        _member(pid, ws)
        cid = _seed_conflict(ws)
        try:
            response = _client(subject, ws).get("/api/conflicts")
            assert response.status_code == 200, response.text
            body = response.json()
            assert [c["id"] for c in body] == [cid]
            assert body[0]["name_a"] == "Acme Holdings"
            assert body[0]["similarity"] == pytest.approx(0.94, abs=1e-6)
            assert body[0]["status"] == "pending"
        finally:
            _cleanup([pid], [ws])

    def test_wire_shape_matches_the_frontend_contract(self, restore_client):
        """`EntityConflict` in `frontend/src/lib/api.ts` reads every one of these.

        The frontend renders `created_at` in the conflict card header
        ("Detected {date}"), and it is declared on the TypeScript type — but it is
        absent from `ConflictResponse`, so the card has always rendered
        `new Date(undefined)`. Asserted here rather than in prose because a field
        the client reads and the server never sends is exactly the class of defect
        a mock swap surfaces late.
        """
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("shape")
        _member(pid, ws)
        _seed_conflict(ws)
        try:
            body = _client(subject, ws).get("/api/conflicts").json()
            assert set(body[0]) >= {
                "id", "name_a", "type_a", "name_b", "type_b",
                "similarity", "quote_a", "quote_b", "sensitivity", "status",
                "created_at",
            }
        finally:
            _cleanup([pid], [ws])

    def test_clearance_bounds_what_is_returned(self, restore_client):
        """The listing filters on `sensitivity <= principal.clearance`.

        That filter is the reason the handler resolves a principal at all, so it is
        the assertion that proves the resolution is real and not decorative.
        """
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("clearance")
        _member(pid, ws, role="investor")
        visible = _seed_conflict(ws, name_a="Visible Co", sensitivity=1)
        _seed_conflict(ws, name_a="Restricted Co", sensitivity=3)
        try:
            body = _client(subject, ws).get("/api/conflicts").json()
            assert [c["id"] for c in body] == [visible]
        finally:
            _cleanup([pid], [ws])

    def test_a_conflict_in_another_workspace_is_not_listed(self, restore_client):
        """Not because the route checks, but because RLS means the row is not there."""
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        mine = _workspace("mine")
        theirs = _workspace("theirs")
        _member(pid, mine)
        _seed_conflict(theirs, name_a="Someone Else Ltd")
        try:
            assert _client(subject, mine).get("/api/conflicts").json() == []
        finally:
            _cleanup([pid], [mine, theirs])

    def test_status_filter_is_honoured(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("status")
        _member(pid, ws)
        _seed_conflict(ws, name_a="Pending Co", status="pending")
        approved = _seed_conflict(ws, name_a="Approved Co", status="approved")
        try:
            client = _client(subject, ws)
            body = client.get("/api/conflicts", params={"status": "approved"}).json()
            assert [c["id"] for c in body] == [approved]
        finally:
            _cleanup([pid], [ws])


class TestRejection:
    """Rejection is the write path that does not need Neo4j, so it is asserted here.

    Approval writes an `ALIAS_OF` edge through the graph driver and belongs with the
    graph integration tests; what is asserted for it below is only that the driver is
    obtained by a name that exists.
    """

    def test_rejecting_marks_the_conflict_and_records_an_audit_event(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("reject")
        _member(pid, ws)
        cid = _seed_conflict(ws)
        try:
            response = _client(subject, ws).post(f"/api/conflicts/{cid}/reject")
            assert response.status_code == 200, response.text
            assert response.json() == {"id": cid, "status": "rejected"}

            with psycopg.connect(settings().postgres_dsn, row_factory=psycopg.rows.dict_row) as conn:
                row = conn.execute(
                    "SELECT status, reviewed_by FROM entity_conflict WHERE id = %s", (cid,)
                ).fetchone()
                assert row["status"] == "rejected"
                assert str(row["reviewed_by"]) == pid

                events = conn.execute(
                    "SELECT action, payload FROM audit_event WHERE aggregate_id = %s", (cid,)
                ).fetchall()
                assert [e["action"] for e in events] == ["status_changed"]
                assert events[0]["payload"]["status"] == "rejected"
        finally:
            _cleanup([pid], [ws])

    def test_rejecting_an_unknown_conflict_is_404(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("missing")
        _member(pid, ws)
        try:
            response = _client(subject, ws).post(f"/api/conflicts/{uuid.uuid4()}/reject")
            assert response.status_code == 404
        finally:
            _cleanup([pid], [ws])


class TestMembershipIsRevalidatedOnWrites:
    """The listing endpoint resolves a principal; the two write endpoints did not.

    `list_conflicts` took `deps.CurrentPrincipal`, which JOINs to an **active**
    membership on every request. `approve_conflict` and `reject_conflict` took
    `deps.current_session` + `deps.current_workspace` instead. Neither of those
    checks membership: `current_session` reports who the caller *claims* to be from
    a signed cookie, and `current_workspace` only asserts the id in it parses.

    So revoking a membership stopped a caller from *reading* the queue immediately,
    and did not stop them from *approving* entries in it until their session
    expired — up to `MAX_SESSION_LIFETIME_SECONDS` (24h). Approval writes an
    `ALIAS_OF` edge into an append-only graph, so the window was on the destructive
    half of the router, not the readable one.

    These assert the *write did not happen*, not merely that a status code changed —
    a 403 with the row already merged would be the same defect with better manners.
    """

    def test_a_revoked_member_cannot_reject(self, restore_client):
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("revoked-reject")
        _member(pid, ws)
        cid = _seed_conflict(ws)
        try:
            client = _client(subject, ws)
            # The session is established while the membership is live, which is the
            # only way to reach the defect: the cookie is minted, *then* access is
            # revoked. A caller who was never a member could not sign in at all.
            _admin(
                "UPDATE membership SET active = false WHERE principal_id = %s AND workspace_id = %s",
                (pid, ws),
            )

            response = client.post(f"/api/conflicts/{cid}/reject")
            assert response.status_code == 403, response.text

            with psycopg.connect(settings().postgres_dsn, row_factory=psycopg.rows.dict_row) as conn:
                row = conn.execute(
                    "SELECT status, reviewed_by FROM entity_conflict WHERE id = %s", (cid,)
                ).fetchone()
                assert row["status"] == "pending"
                assert row["reviewed_by"] is None
        finally:
            _cleanup([pid], [ws])

    def test_a_revoked_member_cannot_approve(self, restore_client):
        """Refused in the dependency, so the graph driver is never opened."""
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("revoked-approve")
        _member(pid, ws)
        cid = _seed_conflict(ws)
        try:
            client = _client(subject, ws)
            _admin(
                "UPDATE membership SET active = false WHERE principal_id = %s AND workspace_id = %s",
                (pid, ws),
            )

            response = client.post(f"/api/conflicts/{cid}/approve")
            assert response.status_code == 403, response.text

            with psycopg.connect(settings().postgres_dsn, row_factory=psycopg.rows.dict_row) as conn:
                row = conn.execute(
                    "SELECT status FROM entity_conflict WHERE id = %s", (cid,)
                ).fetchone()
                assert row["status"] == "pending"
        finally:
            _cleanup([pid], [ws])

    def test_a_refused_write_records_no_audit_event(self, restore_client):
        """`status_changed` on a refusal would make the trail disagree with the row.

        The audit table is append-only, so an event written beside a mutation that
        did not happen cannot be taken back.
        """
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("revoked-audit")
        _member(pid, ws)
        cid = _seed_conflict(ws)
        try:
            client = _client(subject, ws)
            _admin(
                "UPDATE membership SET active = false WHERE principal_id = %s AND workspace_id = %s",
                (pid, ws),
            )
            assert client.post(f"/api/conflicts/{cid}/reject").status_code == 403

            with psycopg.connect(settings().postgres_dsn, row_factory=psycopg.rows.dict_row) as conn:
                events = conn.execute(
                    "SELECT action FROM audit_event WHERE aggregate_id = %s", (cid,)
                ).fetchall()
                assert events == []
        finally:
            _cleanup([pid], [ws])

    def test_the_reviewer_recorded_is_the_resolved_principal(self, restore_client):
        """`reviewer_id` now comes from the principal the database resolved.

        It was `uuid.UUID(request_session.principal_id)` — the id the *cookie*
        carries. On this router the two agree, so nothing observable changes; the
        assertion is here because attribution sourced from the request and
        authorization sourced from the database are two facts that can drift, and
        the audit trail should be stamped with the one that was checked.
        """
        subject = f"sub-{uuid.uuid4()}"
        pid = _principal_with_identity(subject)
        ws = _workspace("reviewer")
        _member(pid, ws)
        cid = _seed_conflict(ws)
        try:
            assert _client(subject, ws).post(f"/api/conflicts/{cid}/reject").status_code == 200

            with psycopg.connect(settings().postgres_dsn, row_factory=psycopg.rows.dict_row) as conn:
                row = conn.execute(
                    "SELECT reviewed_by FROM entity_conflict WHERE id = %s", (cid,)
                ).fetchone()
                assert str(row["reviewed_by"]) == pid

                event = conn.execute(
                    "SELECT actor_principal_id FROM audit_event WHERE aggregate_id = %s", (cid,)
                ).fetchone()
                assert str(event["actor_principal_id"]) == pid
        finally:
            _cleanup([pid], [ws])


def test_every_write_endpoint_on_this_router_resolves_a_principal():
    """The generalisation, so a new handler cannot reintroduce the gap silently.

    `current_session` is a legitimate dependency for a handler that genuinely needs
    only identity, but no mutating endpoint on this router is one of those. Asserted
    over the signatures rather than by calling each route, so a route added without
    a test is still covered.
    """
    import inspect

    offenders = []
    for route in conflicts_api.router.routes:
        methods = getattr(route, "methods", set()) - {"HEAD", "OPTIONS"}
        if methods <= {"GET"}:
            continue
        annotations = inspect.get_annotations(route.endpoint, eval_str=False)
        if "principal" not in annotations:
            offenders.append(f"{sorted(methods)} {route.path} -> {route.endpoint.__name__}")

    assert offenders == []


def test_every_module_attribute_the_router_reaches_for_exists():
    """The generalisation of the two defects above, so the class cannot come back.

    `deps.resolve_principal` and `store.connect_neo4j` were both plausible names for
    functions this module needs and neither was ever defined. Python resolves a
    module attribute at call time, so an import-time check — which is what a test
    that only inspects the OpenAPI paths performs — cannot see either one.

    The approval path in particular is hard to reach from a test that does not have
    Neo4j, which is how `store.connect_neo4j` survived. This asserts the names
    themselves, which needs neither a database nor a graph.
    """
    import ast
    import importlib
    from pathlib import Path

    source = Path(conflicts_api.__file__)
    tree = ast.parse(source.read_text())

    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"

    missing = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            target = aliases.get(node.value.id)
            if target is None:
                continue
            try:
                module = importlib.import_module(target)
            except ImportError:
                continue
            if not hasattr(module, node.attr):
                missing.append(f"{source.name}:{node.lineno}: {node.value.id}.{node.attr} (not in {target})")

    assert missing == []
