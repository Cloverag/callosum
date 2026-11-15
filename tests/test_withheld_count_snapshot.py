"""An ADR-018 list and its withheld count come from one snapshot (#240).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest tests/test_withheld_count_snapshot.py``.

`packs._fetch_items_for_packs` and `meetings.meeting_material` read the visible list and
the withheld count in two statements. `store.pg` runs at READ COMMITTED, where each
statement takes its own snapshot, so a write committed between them yields a list from
before and a count from after: a completeness claim that matches no state the data was
ever in.

Deterministic, not a race: a wrapper commits a write from a second connection right
after the Nth statement. The write is a **move**: un-assign one visible document and
assign one restricted document, in one transaction. The true total is 1 before it and
1 after it, so `len(visible) + withheld == 1` holds at every real snapshot and only a
mix of two snapshots can make it 2.
"""

import contextlib
import hashlib
import os
import uuid

import pytest

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip(
        "set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests",
        allow_module_level=True,
    )

import psycopg

from callosum import store
from callosum.config import settings
from meridian import meetings, packs

pytestmark = pytest.mark.integration

CLEARANCE = 1


def _admin(*statements: tuple[str, tuple]) -> None:
    """Runs the statements in ONE committed transaction, outside the caller's."""
    with psycopg.connect(settings().postgres_dsn) as conn:
        for sql, params in statements:
            conn.execute(sql, params)
        conn.commit()


class _CommitAfter:
    """Delegates to a real connection; commits `write` after the Nth `execute`."""

    def __init__(self, conn, after: int, write) -> None:
        self._conn, self._after, self._write, self._n = conn, after, write, 0

    def execute(self, *args, **kwargs):
        result = self._conn.execute(*args, **kwargs)
        self._n += 1
        if self._n == self._after:
            self._write()
        return result


@pytest.fixture
def world():
    ws = str(uuid.uuid4())
    _admin(("INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s)", (ws, f"snap-{ws[:8]}", ws)))
    meeting = meetings.create_meeting("Snapshot Meeting", workspace_id=ws)

    def doc(title: str, sensitivity: int) -> str:
        did = str(uuid.uuid4())
        _admin((
            "INSERT INTO document (id, workspace_id, title, doc_type, raw_text, content_hash, sensitivity)"
            " VALUES (%s, %s, %s, 'memo', %s, %s, %s)",
            (did, ws, title, title, hashlib.sha256(f"{ws}{title}".encode()).hexdigest(), sensitivity),
        ))
        return did

    visible, restricted = doc("Public deck", 0), doc("Comp review", 4)
    try:
        yield ws, meeting.id, visible, restricted
    finally:
        for table in ("board_pack_item", "board_pack", "meeting_document", "audit_event",
                      "document", "meeting"):
            _admin((f"DELETE FROM {table} WHERE workspace_id = %s", (ws,)))
        _admin(("DELETE FROM workspace WHERE id = %s", (ws,)))


def test_a_pack_list_and_its_withheld_count_share_a_snapshot(world):
    ws, meeting_id, visible, restricted = world
    pack = str(uuid.uuid4())
    _admin(
        ("INSERT INTO board_pack (id, meeting_id, title, workspace_id) VALUES (%s, %s, 'Pack', %s)",
         (pack, meeting_id, ws)),
        ("INSERT INTO board_pack_item (board_pack_id, document_id, position, workspace_id)"
         " VALUES (%s, %s, 1, %s)", (pack, visible, ws)),
    )

    def move():
        _admin(
            ("DELETE FROM board_pack_item WHERE board_pack_id = %s AND document_id = %s", (pack, visible)),
            ("INSERT INTO board_pack_item (board_pack_id, document_id, position, workspace_id)"
             " VALUES (%s, %s, 2, %s)", (pack, restricted, ws)),
        )

    with store.pg(ws) as conn:
        result = packs._fetch_items_for_packs(_CommitAfter(conn, 1, move), [uuid.UUID(pack)], CLEARANCE)

    got = result[pack]
    assert len(got.items) + got.withheld == 1, (
        f"{len(got.items)} visible + {got.withheld} withheld: the list and the count "
        f"were read from different snapshots"
    )


def test_meeting_material_and_its_withheld_count_share_a_snapshot(world, monkeypatch):
    ws, meeting_id, visible, restricted = world
    _admin((
        "INSERT INTO meeting_document (workspace_id, meeting_id, document_id) VALUES (%s, %s, %s)",
        (ws, meeting_id, visible),
    ))

    def move():
        _admin(
            ("DELETE FROM meeting_document WHERE meeting_id = %s AND document_id = %s", (meeting_id, visible)),
            ("INSERT INTO meeting_document (workspace_id, meeting_id, document_id) VALUES (%s, %s, %s)",
             (ws, meeting_id, restricted)),
        )

    real_pg = store.pg

    @contextlib.contextmanager
    def interleaved_pg(*args, **kwargs):
        with real_pg(*args, **kwargs) as conn:
            # Statement 1 is the meeting-exists check; the write lands after statement 2.
            yield _CommitAfter(conn, 2, move)

    monkeypatch.setattr(store, "pg", interleaved_pg)
    material = meetings.meeting_material(meeting_id, clearance=CLEARANCE, workspace_id=ws)

    assert len(material.documents) + material.withheld == 1, (
        f"{len(material.documents)} visible + {material.withheld} withheld: the list and "
        f"the count were read from different snapshots"
    )
