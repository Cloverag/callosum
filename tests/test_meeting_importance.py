import uuid
import pytest
from meridian import meetings
from meridian.api import main
from fastapi.testclient import TestClient

client = TestClient(main.app)


@pytest.mark.integration
def test_meeting_default_importance():
    """Verify meeting defaults to 'routine' importance."""
    w_id = str(uuid.uuid4())
    import psycopg
    from callosum import store
    with psycopg.connect(store.settings().postgres_dsn, row_factory=store.dict_row) as conn:
        conn.execute("INSERT INTO workspace (id, name) VALUES (%s, 'W') ON CONFLICT DO NOTHING", (w_id,))
        conn.commit()
    m = meetings.create_meeting("Default Importance Meeting", workspace_id=w_id)
    assert m.importance == "routine"


@pytest.mark.integration
def test_meeting_custom_importance():
    """Verify custom importance levels ('critical', 'high', 'low')."""
    w_id = str(uuid.uuid4())
    import psycopg
    from callosum import store
    with psycopg.connect(store.settings().postgres_dsn, row_factory=store.dict_row) as conn:
        conn.execute("INSERT INTO workspace (id, name) VALUES (%s, 'W') ON CONFLICT DO NOTHING", (w_id,))
        conn.commit()
    m_critical = meetings.create_meeting("Critical Meeting", workspace_id=w_id, importance="critical")
    assert m_critical.importance == "critical"

    m_updated = meetings.update_meeting(m_critical.id, expected_version=m_critical.version, workspace_id=w_id, importance="high")
    assert m_updated.importance == "high"


def test_invalid_importance_validation():
    """Verify invalid importance string throws MeetingValidationError."""
    w_id = str(uuid.uuid4())
    with pytest.raises(meetings.MeetingValidationError):
        meetings.create_meeting("Invalid Importance", workspace_id=w_id, importance="super_urgent")
