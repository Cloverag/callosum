import uuid
import pytest
import psycopg
from meridian import meetings
from meridian.api import main
from fastapi.testclient import TestClient
from callosum import store

client = TestClient(main.app)


def _wipe_workspace(ws: str) -> None:
    """#184: this file used to leave a workspace + meeting behind every gated run."""
    with psycopg.connect(store.settings().postgres_dsn) as conn:
        conn.execute("DELETE FROM audit_event WHERE workspace_id = %s", (ws,))
        conn.execute("DELETE FROM meeting WHERE workspace_id = %s", (ws,))
        conn.execute("DELETE FROM workspace WHERE id = %s", (ws,))
        conn.commit()


@pytest.mark.integration
def test_meeting_default_importance():
    """Verify meeting defaults to 'routine' importance."""
    w_id = str(uuid.uuid4())
    try:
        with psycopg.connect(store.settings().postgres_dsn, row_factory=store.dict_row) as conn:
            conn.execute("INSERT INTO workspace (id, name) VALUES (%s, 'W') ON CONFLICT DO NOTHING", (w_id,))
            conn.commit()
        m = meetings.create_meeting("Default Importance Meeting", workspace_id=w_id)
        assert m.importance == "routine"
    finally:
        _wipe_workspace(w_id)


@pytest.mark.integration
def test_meeting_custom_importance():
    """Verify custom importance levels ('critical', 'high', 'low')."""
    w_id = str(uuid.uuid4())
    try:
        with psycopg.connect(store.settings().postgres_dsn, row_factory=store.dict_row) as conn:
            conn.execute("INSERT INTO workspace (id, name) VALUES (%s, 'W') ON CONFLICT DO NOTHING", (w_id,))
            conn.commit()
        m_critical = meetings.create_meeting("Critical Meeting", workspace_id=w_id, importance="critical")
        assert m_critical.importance == "critical"

        m_updated = meetings.update_meeting(m_critical.id, expected_version=m_critical.version, workspace_id=w_id, importance="high")
        assert m_updated.importance == "high"
    finally:
        _wipe_workspace(w_id)


def test_invalid_importance_validation():
    """Verify invalid importance string throws MeetingValidationError."""
    w_id = str(uuid.uuid4())
    with pytest.raises(meetings.MeetingValidationError):
        meetings.create_meeting("Invalid Importance", workspace_id=w_id, importance="super_urgent")
