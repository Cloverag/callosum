"""Live-store integration coverage for the P2 BoardPack aggregate (Meridian, checkpoint 3).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``. These tests
exercise the board pack domain against a real Postgres: item positioning, publication immutability,
supersession lineage, document deletion restrictions (ON DELETE RESTRICT), optimistic concurrency, and
Row-Level Security tenant isolation across workspaces.
"""

import os
import uuid

import pytest

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip("set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests", allow_module_level=True)

import psycopg

from callosum.config import settings
from meridian import agenda, meetings, packs
from meridian.packs import (
    DRAFT,
    PUBLISHED,
    BoardPackLockedError,
    BoardPackNotFound,
    BoardPackValidationError,
    StaleBoardPackError,
)

pytestmark = pytest.mark.integration


def _admin(sql: str, params: tuple = ()) -> None:
    """Run a control-plane statement as the superuser (bypasses RLS by design)."""
    with psycopg.connect(settings().postgres_dsn) as conn:
        conn.execute(sql, params)
        conn.commit()


def _new_workspace() -> str:
    ws = str(uuid.uuid4())
    _admin(
        "INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s)",
        (ws, f"test-{ws[:8]}", ws),
    )
    return ws


def _create_test_document(ws: str, title: str = "Test Deck.pdf") -> str:
    doc_id = str(uuid.uuid4())
    _admin(
        """
        INSERT INTO document (id, filename, doc_type, raw_text, sensitivity, workspace_id)
        VALUES (%s, %s, 'board_deck', 'Sample deck content', 1, %s)
        """,
        (uuid.UUID(doc_id), title, uuid.UUID(ws)),
    )
    return doc_id


def _cleanup(*workspace_ids: str) -> None:
    for ws in workspace_ids:
        _admin("DELETE FROM board_pack_item WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM board_pack WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM agenda_item WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM document WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM meeting WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM workspace WHERE id = %s", (ws,))


def test_create_and_get_board_pack():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Pack Meeting", workspace_id=ws)
        doc = _create_test_document(ws, "Q3 Board Deck.pdf")

        pack = packs.create_pack(m.id, "Q3 Pre-read Pack", workspace_id=ws)
        assert pack.meeting_id == m.id
        assert pack.title == "Q3 Pre-read Pack"
        assert pack.status == DRAFT
        assert pack.version_no == 1
        assert pack.version == 1
        assert pack.items == []

        item = packs.add_pack_item(
            pack.id, doc, workspace_id=ws, note="Main presentation"
        )
        assert item.board_pack_id == pack.id
        assert item.document_id == doc
        assert item.position == 1
        assert item.note == "Main presentation"

        fetched = packs.get_pack(pack.id, workspace_id=ws)
        assert len(fetched.items) == 1
        assert fetched.items[0].document_id == doc
    finally:
        _cleanup(ws)


def test_add_and_remove_pack_items():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Item Meeting", workspace_id=ws)
        d1 = _create_test_document(ws, "Deck 1.pdf")
        d2 = _create_test_document(ws, "Deck 2.pdf")

        pack = packs.create_pack(m.id, "Multi-item Pack", workspace_id=ws)

        i1 = packs.add_pack_item(pack.id, d1, workspace_id=ws)
        i2 = packs.add_pack_item(pack.id, d2, workspace_id=ws)
        assert i1.position == 1
        assert i2.position == 2

        # Remove item 1 -> item 2 position shifts down to 1
        packs.remove_pack_item(i1.id, workspace_id=ws)

        fetched = packs.get_pack(pack.id, workspace_id=ws)
        assert len(fetched.items) == 1
        assert fetched.items[0].id == i2.id
        assert fetched.items[0].position == 1
    finally:
        _cleanup(ws)


def test_publish_board_pack_locks_mutations():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Publish Meeting", workspace_id=ws)
        doc = _create_test_document(ws, "Final Deck.pdf")

        pack = packs.create_pack(m.id, "Draft Pack", workspace_id=ws)
        packs.add_pack_item(pack.id, doc, workspace_id=ws)

        # Publish pack
        published = packs.publish_pack(pack.id, expected_version=2, workspace_id=ws)
        assert published.status == PUBLISHED
        assert published.published_at is not None

        # Updating title or adding items to a PUBLISHED pack raises BoardPackLockedError
        d2 = _create_test_document(ws, "Late Add.pdf")
        with pytest.raises(BoardPackLockedError):
            packs.add_pack_item(published.id, d2, workspace_id=ws)

        with pytest.raises(BoardPackLockedError):
            packs.update_pack(published.id, expected_version=3, workspace_id=ws, title="Renamed Pack")
    finally:
        _cleanup(ws)


def test_supersede_published_pack():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Supersede Pack Meeting", workspace_id=ws)
        doc = _create_test_document(ws, "Deck v1.pdf")

        p1 = packs.create_pack(m.id, "Pack v1", workspace_id=ws)
        packs.add_pack_item(p1.id, doc, workspace_id=ws)
        p1 = packs.publish_pack(p1.id, expected_version=2, workspace_id=ws)

        # Supersede p1 with p2
        p2, p1_updated = packs.supersede_pack(
            p1.id, "Pack v2 (Amended)", expected_version=3, workspace_id=ws
        )

        assert p2.title == "Pack v2 (Amended)"
        assert p2.status == DRAFT
        assert p2.version_no == 2
        assert len(p2.items) == 1
        assert p2.items[0].document_id == doc

        assert p1_updated.superseded_by_id == p2.id
    finally:
        _cleanup(ws)


def test_meeting_status_lock_pre_meeting():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Live Meeting", workspace_id=ws)
        m = meetings.transition_status(m.id, meetings.CANCELLED, expected_version=1, workspace_id=ws)

        # Board pack mutations on cancelled meeting raise BoardPackLockedError
        with pytest.raises(BoardPackLockedError):
            packs.create_pack(m.id, "Late Pack", workspace_id=ws)
    finally:
        _cleanup(ws)


def test_document_deletion_restricted():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Restrict Meeting", workspace_id=ws)
        doc = _create_test_document(ws, "Protected.pdf")

        pack = packs.create_pack(m.id, "Protected Pack", workspace_id=ws)
        packs.add_pack_item(pack.id, doc, workspace_id=ws)

        # Hard deleting document in Postgres should fail due to ON DELETE RESTRICT
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            _admin("DELETE FROM document WHERE id = %s", (uuid.UUID(doc),))
    finally:
        _cleanup(ws)


def test_cross_workspace_isolation():
    ws_a = _new_workspace()
    ws_b = _new_workspace()
    try:
        m_a = meetings.create_meeting("Meeting A", workspace_id=ws_a)
        doc_a = _create_test_document(ws_a, "Deck A.pdf")
        p_a = packs.create_pack(m_a.id, "Pack A", workspace_id=ws_a)

        # Workspace B cannot see or modify A's pack
        assert packs.list_packs(m_a.id, workspace_id=ws_b) == []

        with pytest.raises(BoardPackNotFound):
            packs.get_pack(p_a.id, workspace_id=ws_b)

        with pytest.raises(BoardPackNotFound):
            packs.add_pack_item(p_a.id, doc_a, workspace_id=ws_b)
    finally:
        _cleanup(ws_a, ws_b)


def test_optimistic_concurrency():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Concurrency Pack Meeting", workspace_id=ws)
        pack = packs.create_pack(m.id, "Original Pack Title", workspace_id=ws)

        # Update 1 -> version 2
        updated = packs.update_pack(pack.id, expected_version=1, workspace_id=ws, title="New Title")
        assert updated.version == 2

        # Update 2 with stale version 1 -> raises StaleBoardPackError
        with pytest.raises(StaleBoardPackError):
            packs.update_pack(pack.id, expected_version=1, workspace_id=ws, title="Stale Title")
    finally:
        _cleanup(ws)
