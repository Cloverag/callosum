"""The application's behaviour when it is only partly configured.

Fast suite — no database, no live stores.

Both tests here exist because **running the app found what 610 tests did not.** Every
other API test builds its own `FastAPI()` and installs `SessionMiddleware` explicitly,
so no test ever exercised the real `meridian.api.main:app` with a default `.env`. The
first person to follow the quick start got a 500 on every page.
"""

from fastapi.testclient import TestClient


def test_health_engine_does_not_report_a_filesystem_path():
    """It used to return `callosum.__file__`.

    That is an absolute server path on an unauthenticated endpoint — it tells an
    anonymous caller the deployment layout and the operating user's home directory.
    The version answers the question the check exists for without the disclosure.
    """
    from meridian.api.main import app

    body = TestClient(app).get("/health/engine").json()

    assert body["status"] == "ok"
    assert "engine_version" in body
    assert "engine_loaded_from" not in body
    # Belt and braces: no value in the payload may look like a path.
    for value in body.values():
        assert "/" not in str(value), f"a filesystem path leaked in /health/engine: {value!r}"


def test_an_unconfigured_session_is_503_not_500():
    """A missing signing secret is a deployment state, not a crash.

    `SessionMiddleware` is installed only when `MERIDIAN_SESSION_SECRET` is set —
    deliberately, because handing out forgeable cookies is worse than refusing to start
    the feature. But `request.session` then raises `AssertionError`, which surfaced as a
    500 on **every authenticated endpoint**: an internal error, for a configuration
    problem an operator can fix in one line.

    `main.py` already treats missing OIDC configuration this way — the routes mount and
    answer 503. This asserts the session path behaves the same.
    """
    from fastapi import FastAPI

    from meridian.api import documents as documents_api
    from meridian.api import errors

    # An app WITHOUT SessionMiddleware, which is exactly what `main.py` builds when the
    # secret is unset.
    app = FastAPI()
    app.include_router(documents_api.router)
    errors.install_exception_handlers(app)

    response = TestClient(app, raise_server_exceptions=False).get("/api/documents")

    body = response.json()
    err_data = body.get("error", body.get("detail", {}))
    assert response.status_code == 503, "an unconfigured session must not be a 500"
    assert err_data["code"] == "session_not_configured"
    # The message has to name the fix. "Service Unavailable" alone sends an operator
    # looking at the database.
    assert "MERIDIAN_SESSION_SECRET" in err_data["detail"]
