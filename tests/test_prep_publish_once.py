"""`publish_preread` records a `published` event only when it publishes (P5, #226).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest tests/test_prep_publish_once.py``.

At `7f8a84b` it wrote a `published` event on every call, including for a pack that was
already published, so a retry (or a second click) put a second "published" row in an
append-only trail for something that did not happen again.
"""

import os
import uuid

import pytest

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip("set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests", allow_module_level=True)

import psycopg

from callosum import identity
from callosum.config import settings
from meridian import audit, meetings, prep

pytestmark = pytest.mark.integration


def _admin(sql: str, params: tuple = ()) -> None:
    with psycopg.connect(settings().postgres_dsn) as conn:
        conn.execute(sql, params)
        conn.commit()


@pytest.fixture
def world():
    ws, actor = str(uuid.uuid4()), str(uuid.uuid4())
    clearance = identity.ROLE_TO_CLEARANCE["director"]
    _admin("INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s)", (ws, f"pre-{ws[:8]}", ws))
    _admin(
        "INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, 'director', %s)",
        (actor, f"Actor {actor[:6]}", clearance),
    )
    _admin(
        "INSERT INTO membership (principal_id, workspace_id, role, clearance, active)"
        " VALUES (%s, %s, 'director', %s, true)",
        (actor, ws, clearance),
    )
    try:
        yield ws, actor
    finally:
        for table in ("audit_event", "board_pack", "meeting", "membership"):
            _admin(f"DELETE FROM {table} WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM workspace WHERE id = %s", (ws,))
        _admin("DELETE FROM principal WHERE id = %s", (actor,))


def _published_events(ws: str, pack_id: str) -> list:
    return [
        e
        for e in audit.list_audit_events(aggregate_type="board_pack", aggregate_id=pack_id, workspace_id=ws)
        if e.action == "published"
    ]


def test_publishing_twice_records_one_event_and_keeps_the_first_timestamp(world):
    ws, actor = world
    m = meetings.create_meeting("Q3", workspace_id=ws)
    pack_id = str(uuid.uuid4())
    _admin(
        "INSERT INTO board_pack (id, meeting_id, title, status, version_no, workspace_id)"
        " VALUES (%s, %s, 'Pack', 'draft', 1, %s)",
        (pack_id, m.id, ws),
    )

    first = prep.publish_preread(m.id, workspace_id=ws, actor_id=actor)
    with psycopg.connect(settings().postgres_dsn) as conn:
        stamp = conn.execute("SELECT published_at FROM board_pack WHERE id = %s", (pack_id,)).fetchone()[0]

    second = prep.publish_preread(m.id, workspace_id=ws, actor_id=actor)

    assert first == second  # the answer is still true, so a retry gets it
    assert second["status"] == "published"
    assert len(_published_events(ws, pack_id)) == 1
    with psycopg.connect(settings().postgres_dsn) as conn:
        again = conn.execute("SELECT published_at FROM board_pack WHERE id = %s", (pack_id,)).fetchone()[0]
    assert again == stamp


def test_publishing_with_no_pack_still_refuses_and_records_nothing(world):
    ws, actor = world
    m = meetings.create_meeting("Empty", workspace_id=ws)
    with pytest.raises(prep.MeetingPrepError):
        prep.publish_preread(m.id, workspace_id=ws, actor_id=actor)
    assert audit.list_audit_events(aggregate_type="board_pack", workspace_id=ws) == []
