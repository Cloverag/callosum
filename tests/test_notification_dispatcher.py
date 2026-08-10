import uuid
import pytest
from datetime import timedelta
from meridian import notifications, commitments, meetings, decisions
from meridian.api import main
from fastapi.testclient import TestClient

client = TestClient(main.app)


def test_retry_delay_calculation():
    """Verify exponential backoff calculation."""
    assert notifications.calculate_retry_delay(0) == timedelta(minutes=0)
    assert notifications.calculate_retry_delay(1) == timedelta(minutes=1)
    assert notifications.calculate_retry_delay(2) == timedelta(minutes=2)
    assert notifications.calculate_retry_delay(3) == timedelta(minutes=4)
    assert notifications.calculate_retry_delay(4) == timedelta(minutes=8)
    assert notifications.calculate_retry_delay(5) == timedelta(minutes=16)


def test_notifications_api_routes_registered():
    """Verify notification routes exist in OpenAPI spec."""
    paths = main.app.openapi()["paths"]
    assert "/api/notifications/pending" in paths
    assert "/api/notifications/dispatch" in paths


def test_notification_dispatch_flow():
    """Test batch notification dispatching workflow."""
    w_id = str(uuid.uuid4())
    m_id = str(uuid.uuid4())
    d_id = str(uuid.uuid4())
    member_id = str(uuid.uuid4())

    import psycopg
    with psycopg.connect(commitments.store.settings().postgres_dsn, row_factory=commitments.store.dict_row) as conn:
        conn.execute("INSERT INTO workspace (id, name) VALUES (%s, 'Test W')", (w_id,))
        conn.execute("INSERT INTO board_member (id, workspace_id, full_name, contact_email, role) VALUES (%s, %s, 'Director', 'dir@test.com', 'director')", (member_id, w_id))
        conn.execute("INSERT INTO meeting (id, workspace_id, title, scheduled_start) VALUES (%s, %s, 'Meeting', now())", (m_id, w_id))
        conn.execute("INSERT INTO decision (id, workspace_id, meeting_id, title) VALUES (%s, %s, %s, 'Decision')", (d_id, w_id, m_id))

    # Create a commitment
    c = commitments.create_commitment("Decision title", owner_board_member_id=member_id, decision_id=d_id, workspace_id=w_id)
    assert c.delivery_status == commitments.PENDING

    # Dispatch pending notifications
    res = notifications.dispatch_pending_notifications(workspace_id=w_id)
    assert res["dispatched"] >= 1

    # Verify commitment status updated to delivered
    updated_c = commitments.get_commitment(c.id, workspace_id=w_id)
    assert updated_c.delivery_status == commitments.DELIVERED
    assert updated_c.external_system == "slack_webhook"
    assert updated_c.external_task_id is not None
