"""Public write surfaces are not unlimited, and docs are off in production."""

from fastapi.testclient import TestClient

from meridian.api import limits
from meridian.api.main import app, docs_enabled


def test_allow_trips_after_the_limit():
    limits.reset()
    assert limits.allow("k", limit=2, window_s=60.0) is True
    assert limits.allow("k", limit=2, window_s=60.0) is True
    assert limits.allow("k", limit=2, window_s=60.0) is False


def test_allow_recovers_after_the_window():
    limits.reset()
    assert limits.allow("w", limit=1, window_s=10.0, now=100.0) is True
    assert limits.allow("w", limit=1, window_s=10.0, now=100.5) is False
    assert limits.allow("w", limit=1, window_s=10.0, now=111.0) is True


def test_docs_enabled_is_false_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("MERIDIAN_EXPOSE_DOCS", raising=False)
    assert docs_enabled() is False


def test_docs_can_be_reopened_explicitly(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("MERIDIAN_EXPOSE_DOCS", "true")
    assert docs_enabled() is True


def test_health_sets_security_headers():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in response.headers["content-security-policy"]
