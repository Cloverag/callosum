"""RED tests: a board pack must not widen who can read a document (P2 checkpoint 3, issue #23).

These tests are expected to FAIL against the current `meridian/packs.py`. They are the
executable form of the CP3 exit criterion that has no implementation yet:

    Putting a document into a pack must not widen who can read it. Pack-item reads stay
    subject to the clearance filter on `document.sensitivity`, pushed into the WHERE
    clause (Invariant #1 — filter before retrieval). A member without clearance must see
    the pack *without* that item, and no title, count, or placeholder may leak that
    something was withheld.

Today `packs.py` contains no reference to `sensitivity`, `clearance`, or any caller
identity, and `_fetch_items_for_packs()` runs an unfiltered

    SELECT * FROM board_pack_item WHERE board_pack_id = ANY(%s)

with no join to `document`. So every caller receives every item regardless of clearance.

`clearance: int | None` is a PROPOSED parameter name, not a mandated one — rename it
freely. What must not change is the behaviour these tests describe. Until the parameter
exists these fail with `TypeError: unexpected keyword argument`, which is itself the
finding: the read API cannot currently express "who is asking", so there is nowhere for
the filter to live.

Run: ``CALLOSUM_RUN_INTEGRATION=1 pytest tests/test_board_pack_rbac.py -v``
"""

import os
import uuid

import pytest

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip("set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests", allow_module_level=True)

import psycopg

from callosum.config import settings
from meridian import meetings, packs

pytestmark = pytest.mark.integration

# sensitivity table: 0 public · 1 investor · 2 internal · 3 confidential · 4 restricted
PUBLIC = 0
INVESTOR = 1
RESTRICTED = 4


def _admin(sql: str, params: tuple = ()) -> None:
    """Run a control-plane statement as the superuser (bypasses RLS by design)."""
    with psycopg.connect(settings().postgres_dsn) as conn:
        conn.execute(sql, params)
        conn.commit()


def _new_workspace() -> str:
    ws = str(uuid.uuid4())
    _admin(
        "INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s)",
        (ws, f"rbac-{ws[:8]}", ws),
    )
    return ws


def _document(ws: str, title: str, sensitivity: int) -> str:
    doc_id = str(uuid.uuid4())
    _admin(
        """
        INSERT INTO document (id, title, doc_type, raw_text, content_hash, sensitivity, workspace_id)
        VALUES (%s, %s, 'board_deck', 'body', %s, %s, %s)
        """,
        (uuid.UUID(doc_id), title, doc_id, sensitivity, uuid.UUID(ws)),
    )
    return doc_id


def _cleanup(*workspace_ids: str) -> None:
    for ws in workspace_ids:
        _admin("DELETE FROM board_pack_item WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM board_pack WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM document WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM meeting WHERE workspace_id = %s", (ws,))
        _admin("DELETE FROM workspace WHERE id = %s", (ws,))


def _pack_with_mixed_sensitivity(ws: str) -> tuple[str, str, str]:
    """A draft pack holding one public document and one restricted document."""
    m = meetings.create_meeting("Q3 Board Meeting", workspace_id=ws)
    pack = packs.create_pack(m.id, "Q3 Pre-read", workspace_id=ws)

    public_doc = _document(ws, "Agenda and logistics.pdf", PUBLIC)
    restricted_doc = _document(ws, "Executive compensation review.pdf", RESTRICTED)

    packs.add_pack_item(pack.id, public_doc, workspace_id=ws, position=1)
    packs.add_pack_item(pack.id, restricted_doc, workspace_id=ws, position=2)

    return pack.id, public_doc, restricted_doc


def test_get_pack_excludes_items_above_caller_clearance():
    """An investor-clearance reader must not receive the restricted item at all."""
    ws = _new_workspace()
    try:
        pack_id, public_doc, restricted_doc = _pack_with_mixed_sensitivity(ws)

        visible = packs.get_pack(pack_id, workspace_id=ws, clearance=INVESTOR)

        doc_ids = {i.document_id for i in visible.items}
        assert public_doc in doc_ids, "the public document must remain visible"
        assert restricted_doc not in doc_ids, (
            "RBAC LAUNDERING: a restricted document became readable because it was "
            "placed in a board pack"
        )
    finally:
        _cleanup(ws)


def test_pack_leaks_no_count_or_placeholder_for_withheld_items():
    """Withheld items vanish. They do not appear as a count, a gap, or a placeholder.

    The pack holds two items. An investor-clearance reader must see exactly one, and
    the positions they see must be contiguous from 1 — a gap at position 2 would tell
    them something exists that they may not read, which is the leak restated.
    """
    ws = _new_workspace()
    try:
        pack_id, _, _ = _pack_with_mixed_sensitivity(ws)

        visible = packs.get_pack(pack_id, workspace_id=ws, clearance=INVESTOR)

        assert len(visible.items) == 1, (
            f"expected 1 visible item, got {len(visible.items)} — the count itself "
            "discloses the withheld document"
        )
        assert [i.position for i in visible.items] == [1], (
            "positions must not leave a hole where a withheld item was"
        )
    finally:
        _cleanup(ws)


def test_full_clearance_reader_sees_every_item():
    """The filter must not over-apply: a fully cleared reader still sees both items."""
    ws = _new_workspace()
    try:
        pack_id, public_doc, restricted_doc = _pack_with_mixed_sensitivity(ws)

        visible = packs.get_pack(pack_id, workspace_id=ws, clearance=RESTRICTED)

        doc_ids = {i.document_id for i in visible.items}
        assert doc_ids == {public_doc, restricted_doc}
    finally:
        _cleanup(ws)


def test_list_packs_applies_the_same_filter_as_get_pack():
    """`list_packs` is a second read path and must not be a way around the filter.

    Two entry points to the same rows is exactly how a filter gets applied in one place
    and forgotten in the other, so this asserts the two agree.
    """
    ws = _new_workspace()
    try:
        pack_id, public_doc, restricted_doc = _pack_with_mixed_sensitivity(ws)
        meeting_id = packs.get_pack(pack_id, workspace_id=ws).meeting_id

        listed = packs.list_packs(meeting_id, workspace_id=ws, clearance=INVESTOR)

        assert len(listed) == 1
        doc_ids = {i.document_id for i in listed[0].items}
        assert doc_ids == {public_doc}, (
            "list_packs bypassed the clearance filter that get_pack applies"
        )
    finally:
        _cleanup(ws)
