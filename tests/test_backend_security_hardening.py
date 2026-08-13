import os
import uuid
import pytest
import psycopg
from fastapi.exceptions import HTTPException

from callosum import store, retrieve
from meridian.api import errors, deps
from meridian.api.errors import ApiError


def test_dev_auto_auth_environment_guard(monkeypatch):
    """C-2: Dev auto-auth must fail if ENVIRONMENT is set to production."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("MERIDIAN_DEV_AUTO_AUTH", "true")

    class FakeRequest:
        session = {}

    req = FakeRequest()
    with pytest.raises(HTTPException) as exc_info:
        deps.current_session(req)

    assert exc_info.value.status_code == 401


def test_error_response_envelope_format():
    """C-1: ApiError.as_response must conform strictly to {"error": {"code": ..., "detail": ...}}."""
    err = ApiError(403, "forbidden", "Not available to you.")
    resp = err.as_response()
    assert "error" in resp
    assert resp["error"]["code"] == "forbidden"
    assert resp["error"]["detail"] == "Not available to you."


def test_query_log_workspace_scoping():
    """H-2: _log must populate workspace_id in query_log."""
    principal = retrieve.Principal(
        id=uuid.uuid4(),
        name="Test Principal",
        role="founder",
        clearance=4,
        workspace_id="11111111-1111-1111-1111-111111111111",
    )
    answer = retrieve.Answer(
        text="Test answer",
        evidence=[],
        graph_facts=[],
        plan={},
        withheld=0,
        latency_ms=12,
    )

    class FakeConn:
        def __init__(self):
            self.last_query = None
            self.last_params = None

        def execute(self, query, params):
            self.last_query = query
            self.last_params = params

    conn = FakeConn()
    retrieve._log(conn, "What is the strategy?", principal, answer)

    assert "workspace_id" in conn.last_query
    assert conn.last_params[0] == "11111111-1111-1111-1111-111111111111"


# H-1 (`acl_grant` in the retrieval predicates) is deliberately not tested here, because
# the predicate it tested has been reverted. `acl_grant` has no writer anywhere in the
# codebase — no seed, no `callosum init`, no domain module, no endpoint — so the `EXISTS`
# subquery was always false and the widening never took effect. The mechanism gate ran
# byte-identical on 2026-08-13 for exactly that reason, which is evidence the change was
# inert, not evidence it was safe.
#
# The test that stood here asserted `"acl_grant" in <sql string>` against a fake
# connection: it proved the source contained a word, not that a grant widens access or
# that its absence denies. If grant-based access becomes a real feature, rules.md §1
# requires it arrive as a tenancy predicate that *removes* rows, with a failing test
# first — one that inserts a grant and proves the widening, and one that proves the
# fail-closed default without it.


def test_session_absolute_expiration():
    """H-8: Sessions older than 24 hours must expire and return None."""
    from meridian.api import session as sess

    s = {}
    sess.establish(s, principal_id=str(uuid.uuid4()), provider="test", subject="test_sub")
    assert sess.read(s) is not None

    # Artificially age the session past 24 hours
    s[sess.CREATED_AT] = s[sess.CREATED_AT] - 90000.0
    assert sess.read(s) is None


def test_conflicts_api_router_registered():
    """H-15: /api/conflicts route must be registered in meridian.api.main."""
    from meridian.api import main
    paths = main.app.openapi()["paths"]
    assert any("/api/conflicts" in p for p in paths)


def test_composite_tenant_foreign_key_constraint():
    """Issue #41: Cross-tenant foreign key reference must fail composite FK constraint."""
    w1 = str(uuid.uuid4())
    w2 = str(uuid.uuid4())
    meeting_id = uuid.uuid4()
    item_id = uuid.uuid4()

    with psycopg.connect(store.settings().postgres_dsn, row_factory=store.dict_row) as conn:
        conn.execute("INSERT INTO workspace (id, name) VALUES (%s, 'W1')", (w1,))
        conn.execute("INSERT INTO workspace (id, name) VALUES (%s, 'W2')", (w2,))

        # Create meeting in workspace w1 (bypassing RLS as superuser to test FK constraint)
        conn.execute(
            """
            INSERT INTO meeting (id, title, scheduled_start, workspace_id)
            VALUES (%s, 'Meeting W1', now(), %s)
            """,
            (meeting_id, w1),
        )

        # Attempt to insert agenda item referencing meeting_id but workspace w2
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            conn.execute(
                """
                INSERT INTO agenda_item (id, meeting_id, title, position, workspace_id)
                VALUES (%s, %s, 'Cross-Tenant Item', 1, %s)
                """,
                (item_id, meeting_id, w2),
            )


