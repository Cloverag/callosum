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
    CONFIDENTIAL_CLEARANCE,
    DRAFT,
    INVESTOR_CLEARANCE,
    PUBLISHED,
    PUBLIC_CLEARANCE,
    RESTRICTED_CLEARANCE,
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
        INSERT INTO document (id, title, doc_type, raw_text, content_hash, sensitivity, workspace_id)
        VALUES (%s, %s, 'board_deck', 'Sample deck content', %s, 1, %s)
        """,
        (uuid.UUID(doc_id), title, doc_id, uuid.UUID(ws)),
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

        fetched = packs.get_pack(pack.id, workspace_id=ws, clearance=RESTRICTED_CLEARANCE)
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

        fetched = packs.get_pack(pack.id, workspace_id=ws, clearance=RESTRICTED_CLEARANCE)
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
        published = packs.publish_pack(pack.id, expected_version=2, workspace_id=ws, clearance=RESTRICTED_CLEARANCE)
        assert published.status == PUBLISHED
        assert published.published_at is not None

        # Updating title or adding items to a PUBLISHED pack raises BoardPackLockedError
        d2 = _create_test_document(ws, "Late Add.pdf")
        with pytest.raises(BoardPackLockedError):
            packs.add_pack_item(published.id, d2, workspace_id=ws)

        with pytest.raises(BoardPackLockedError):
            packs.update_pack(published.id, expected_version=3, workspace_id=ws, title="Renamed Pack", clearance=RESTRICTED_CLEARANCE)
    finally:
        _cleanup(ws)


def test_supersede_published_pack():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Supersede Pack Meeting", workspace_id=ws)
        doc = _create_test_document(ws, "Deck v1.pdf")

        p1 = packs.create_pack(m.id, "Pack v1", workspace_id=ws)
        packs.add_pack_item(p1.id, doc, workspace_id=ws)
        p1 = packs.publish_pack(p1.id, expected_version=2, workspace_id=ws, clearance=RESTRICTED_CLEARANCE)

        # Supersede p1 with p2
        p2, p1_updated = packs.supersede_pack(
            p1.id, "Pack v2 (Amended)", expected_version=3, workspace_id=ws, clearance=RESTRICTED_CLEARANCE
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
        assert packs.list_packs(m_a.id, workspace_id=ws_b, clearance=RESTRICTED_CLEARANCE) == []

        with pytest.raises(BoardPackNotFound):
            packs.get_pack(p_a.id, workspace_id=ws_b, clearance=RESTRICTED_CLEARANCE)

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
        updated = packs.update_pack(pack.id, expected_version=1, workspace_id=ws, title="New Title", clearance=RESTRICTED_CLEARANCE)
        assert updated.version == 2

        # Update 2 with stale version 1 -> raises StaleBoardPackError
        with pytest.raises(StaleBoardPackError):
            packs.update_pack(pack.id, expected_version=1, workspace_id=ws, title="Stale Title", clearance=RESTRICTED_CLEARANCE)
    finally:
        _cleanup(ws)


def test_board_pack_validation_errors():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Validation Pack Meeting", workspace_id=ws)
        d1 = _create_test_document(ws, "Doc 1.pdf")

        # Empty title
        with pytest.raises(BoardPackValidationError):
            packs.create_pack(m.id, "   ", workspace_id=ws)

        p = packs.create_pack(m.id, "Valid Pack Title", workspace_id=ws)

        # Invalid status filter
        with pytest.raises(BoardPackValidationError):
            packs.list_packs(m.id, workspace_id=ws, status="INVALID_STATUS", clearance=RESTRICTED_CLEARANCE)

        # No fields to update
        with pytest.raises(BoardPackValidationError):
            packs.update_pack(p.id, expected_version=1, workspace_id=ws, clearance=RESTRICTED_CLEARANCE)

        # Superseding a draft pack (only published packs can be superseded)
        with pytest.raises(BoardPackValidationError):
            packs.supersede_pack(p.id, "New Title", expected_version=1, workspace_id=ws, clearance=RESTRICTED_CLEARANCE)
    finally:
        _cleanup(ws)


def test_reorder_pack_items():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Reorder Pack Meeting", workspace_id=ws)
        d1 = _create_test_document(ws, "Doc 1.pdf")
        d2 = _create_test_document(ws, "Doc 2.pdf")
        d3 = _create_test_document(ws, "Doc 3.pdf")

        p = packs.create_pack(m.id, "Reorder Pack", workspace_id=ws)
        i1 = packs.add_pack_item(p.id, d1, workspace_id=ws)
        i2 = packs.add_pack_item(p.id, d2, workspace_id=ws)
        i3 = packs.add_pack_item(p.id, d3, workspace_id=ws)

        # Reorder to i3, i1, i2
        reordered = packs.reorder_pack_items(p.id, [i3.id, i1.id, i2.id], workspace_id=ws, clearance=RESTRICTED_CLEARANCE)
        item_order = [it.id for it in reordered.items]
        assert item_order == [i3.id, i1.id, i2.id]
        assert [it.position for it in reordered.items] == [1, 2, 3]
    finally:
        _cleanup(ws)


def test_duplicate_document_rejection():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Dup Doc Meeting", workspace_id=ws)
        d1 = _create_test_document(ws, "Single Doc.pdf")

        p = packs.create_pack(m.id, "Dup Doc Pack", workspace_id=ws)
        packs.add_pack_item(p.id, d1, workspace_id=ws)

        # Adding same document twice raises BoardPackValidationError
        with pytest.raises(BoardPackValidationError):
            packs.add_pack_item(p.id, d1, workspace_id=ws)
    finally:
        _cleanup(ws)


def test_mismatched_agenda_item_rejection():
    ws = _new_workspace()
    try:
        m1 = meetings.create_meeting("Meeting 1", workspace_id=ws)
        m2 = meetings.create_meeting("Meeting 2", workspace_id=ws)
        d1 = _create_test_document(ws, "Doc 1.pdf")
        ag2 = agenda.create_agenda_item(m2.id, "Agenda Item for Meeting 2", workspace_id=ws)

        p1 = packs.create_pack(m1.id, "Pack for Meeting 1", workspace_id=ws)

        # Attaching m2's agenda item to m1's pack raises BoardPackValidationError
        with pytest.raises(BoardPackValidationError):
            packs.add_pack_item(p1.id, d1, workspace_id=ws, agenda_item_id=ag2.id)
    finally:
        _cleanup(ws)


def _create_restricted_test_document(ws: str, title: str = "Confidential Deck.pdf", sensitivity: int = 3) -> str:
    doc_id = str(uuid.uuid4())
    _admin(
        """
        INSERT INTO document (id, title, doc_type, raw_text, content_hash, sensitivity, workspace_id)
        VALUES (%s, %s, 'board_deck', 'Confidential financial details', %s, %s, %s)
        """,
        (uuid.UUID(doc_id), title, doc_id, sensitivity, uuid.UUID(ws)),
    )
    return doc_id


def test_board_pack_rbac_clearance_filtering():
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("RBAC Pack Meeting", workspace_id=ws)
        # `_create_test_document` writes sensitivity 1, which is `investor`, not
        # `public` — naming it accurately here matters, because the whole test is
        # an assertion about which level sees what.
        investor_doc = _create_test_document(ws, "Quarterly Overview.pdf")
        confidential_doc = _create_restricted_test_document(
            ws, "Restricted Financials.pdf", sensitivity=CONFIDENTIAL_CLEARANCE
        )

        p = packs.create_pack(m.id, "Q3 Board Package", workspace_id=ws)
        packs.add_pack_item(p.id, investor_doc, workspace_id=ws, note="Investor item")
        packs.add_pack_item(p.id, confidential_doc, workspace_id=ws, note="Confidential item")

        # Full clearance sees both items.
        full_pack = packs.get_pack(p.id, workspace_id=ws, clearance=RESTRICTED_CLEARANCE)
        assert len(full_pack.items) == 2

        # Investor clearance sees only the investor item — no title, note, or count
        # leak of the confidential one.
        restricted_pack = packs.get_pack(p.id, workspace_id=ws, clearance=INVESTOR_CLEARANCE)
        assert len(restricted_pack.items) == 1
        assert restricted_pack.items[0].document_id == investor_doc

        # Same for list_packs: it is a second read path, not a way around the filter.
        listed_packs = packs.list_packs(m.id, workspace_id=ws, clearance=INVESTOR_CLEARANCE)
        assert len(listed_packs) == 1
        assert len(listed_packs[0].items) == 1
        assert listed_packs[0].items[0].document_id == investor_doc

        # PUBLIC_CLEARANCE is the floor, and it is 0 — not 1. A reader at the very
        # bottom of the ladder sees neither document. This is the case that would
        # have failed silently while PUBLIC_CLEARANCE was defined as the investor
        # level: "public" would have admitted investor material.
        public_pack = packs.get_pack(p.id, workspace_id=ws, clearance=PUBLIC_CLEARANCE)
        assert public_pack.items == []
    finally:
        _cleanup(ws)


def test_pack_item_positions_leave_no_hole_where_an_item_was_withheld():
    """Withheld items leave no gap in the position sequence.

    The restricted document is deliberately FIRST here. Filtering the last item
    happens to leave a contiguous sequence by luck, so a test that only removes a
    trailing item passes without proving anything. Removing the first one is the
    case that exposes whether positions are renumbered: returning [2, 3] tells the
    reader a position 1 exists which they may not see, and lets them count the
    holes — the same disclosure as a placeholder, just quieter.
    """
    ws = _new_workspace()
    try:
        m = meetings.create_meeting("Position Gap Meeting", workspace_id=ws)
        p = packs.create_pack(m.id, "Q3 Board Package", workspace_id=ws)

        restricted = _create_restricted_test_document(
            ws, "Compensation review.pdf", sensitivity=RESTRICTED_CLEARANCE
        )
        packs.add_pack_item(p.id, restricted, workspace_id=ws, position=1)
        packs.add_pack_item(p.id, _create_test_document(ws, "Agenda.pdf"), workspace_id=ws, position=2)
        packs.add_pack_item(p.id, _create_test_document(ws, "Metrics.pdf"), workspace_id=ws, position=3)

        visible = packs.get_pack(p.id, workspace_id=ws, clearance=INVESTOR_CLEARANCE)
        assert len(visible.items) == 2
        assert [i.position for i in visible.items] == [1, 2], (
            "withheld item left a hole in the position sequence"
        )

        # The filter must not renumber away the real ordering for a cleared reader.
        full = packs.get_pack(p.id, workspace_id=ws, clearance=RESTRICTED_CLEARANCE)
        assert [i.position for i in full.items] == [1, 2, 3]
    finally:
        _cleanup(ws)
