"""HTTP Q&A is session-gated and does not take clearance from the client."""

from fastapi.testclient import TestClient

from meridian.api.main import app


def test_ask_route_is_registered():
    paths = app.openapi()["paths"]
    assert "/api/ask" in paths
    assert "post" in paths["/api/ask"]


def test_ask_without_a_session_is_not_success():
    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/ask", json={"question": "Why did we reject Pricing Model B?"}
    )
    assert response.status_code in (401, 403, 503)
    assert response.status_code != 200


def test_demo_impersonation_is_absent_from_openapi():
    """A disabled (or enabled) selector must not advertise itself in the spec."""
    paths = app.openapi()["paths"]
    assert not any(p.startswith("/auth/demo") for p in paths)
