import uuid
import pytest
from datetime import datetime, timezone
from meridian import prep, meetings, packs
from meridian.api import main
from fastapi.testclient import TestClient

client = TestClient(main.app)


def test_prep_api_router_registered():
    """Verify prep routes are registered in OpenAPI spec."""
    paths = main.app.openapi()["paths"]
    assert any("/api/meetings/{meeting_id}/readiness" in p for p in paths)
    assert any("/api/meetings/{meeting_id}/agenda-suggestions" in p for p in paths)
    assert any("/api/meetings/{meeting_id}/publish-preread" in p for p in paths)
