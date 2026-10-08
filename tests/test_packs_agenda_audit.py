"""Board-pack and agenda mutations leave an append-only trail (P5 CP5A, #226).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest tests/test_packs_agenda_audit.py``.

`meridian/packs.py` and `meridian/agenda.py` called `record_audit_event` 0 times at
`7f8a84b`, so the seven pack mutations and four agenda mutations changed what the board
reads and in what order with no record of who did it. These pin one event per mutation,
the actor, the payload discipline, and — the part a coverage count cannot show — that a
*refused* write records nothing. The DB-free guard is `test_packs_agenda_audit_static.py`.
"""

import os
import uuid

import pytest

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip(
        "set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests",
        allow_module_level=True,
    )

import psycopg

from callosum import identity
from callosum.config import settings
from meridian import agenda, audit, meetings, packs, prep
from meridian.agenda import AgendaItemNotFound, StaleAgendaItemError
from meridian.packs import RESTRICTED_CLEARANCE, BoardPackLockedError, StaleBoardPackError

pytestmark = pytest.mark.integration


def _admin(sql: str, params: tuple = ()) -> None:
    with psycopg.connect(settings().postgres_dsn) as conn:
        conn.execute(sql, params)
        conn.commit()


class _World:
    """A workspace with one actor who holds an active membership in it."""

    def __init__(self) -> None:
        self.ws = str(uuid.uuid4())
        self.actor = str(uuid.uuid4())
        _admin(
            "INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s)",
            (self.ws, f"ppa-{self.ws[:8]}", self.ws),
        )
        clearance = identity.ROLE_TO_CLEARANCE["director"]
        _admin(
            "INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, 'director', %s)",
            (self.actor, f"Audit Actor {self.actor[:6]}", clearance),
        )
        # `record_audit_event` refuses an actor with no active membership here.
        _admin(
            "INSERT INTO membership (principal_id, workspace_id, role, clearance, active)"
            " VALUES (%s, %s, 'director', %s, true)",
            (self.actor, self.ws, clearance),
        )

    def meeting(self) -> str:
        return meetings.create_meeting("Audit Meeting", workspace_id=self.ws).id

    def document(self) -> str:
        doc = str(uuid.uuid4())
        _admin(
            "INSERT INTO document (id, title, doc_type, raw_text, content_hash, sensitivity,"
            " workspace_id) VALUES (%s, 'Deck.pdf', 'board_deck', 'x', %s, 1, %s)",
            (doc, doc, self.ws),
        )
        return doc

    def events(self, aggregate_type: str, aggregate_id: str | None = None) -> list:
        return audit.list_audit_events(
            aggregate_type=aggregate_type, aggregate_id=aggregate_id, workspace_id=self.ws
        )

    def all_events(self) -> list:
        return [
            e
            for t in ("board_pack", "agenda_item", "meeting")
            for e in self.events(t)
            # meeting events from create_meeting itself are not this checkpoint's
            if not (t == "meeting" and e.action != "reordered")
        ]

    def close(self) -> None:
        for table in ("audit_event", "board_pack_item", "board_pack", "agenda_item", "document",
                      "meeting", "membership"):
            _admin(f"DELETE FROM {table} WHERE workspace_id = %s", (self.ws,))
        _admin("DELETE FROM workspace WHERE id = %s", (self.ws,))
        _admin("DELETE FROM principal WHERE id = %s", (self.actor,))


@pytest.fixture
def w():
    world = _World()
    try:
        yield world
    finally:
        world.close()


def _actions(events) -> list[str]:
    return sorted(e.action for e in events)


# ---------------------------------------------------------------- board packs


def test_create_update_publish_are_audited_with_the_actor(w):
    a, ws = w.actor, w.ws
    pack = packs.create_pack(w.meeting(), "Q3 Pack", workspace_id=ws, actor_principal_id=a)
    renamed = packs.update_pack(
        pack.id, expected_version=pack.version, title="Q3 Pre-read", workspace_id=ws,
        clearance=RESTRICTED_CLEARANCE, actor_principal_id=a,
    )
    packs.publish_pack(
        pack.id, expected_version=renamed.version, workspace_id=ws,
        clearance=RESTRICTED_CLEARANCE, actor_principal_id=a,
    )

    events = w.events("board_pack", pack.id)
    assert _actions(events) == ["created", "published", "updated"]
    assert all(str(e.actor_principal_id) == a for e in events)
    upd = next(e for e in events if e.action == "updated")
    assert upd.payload["changed_fields"] == ["title"]
    assert upd.payload["title"] == "Q3 Pre-read"
    pub = next(e for e in events if e.action == "published")
    assert pub.payload["status"] == "published"
    assert pub.payload["version_no"] == 1


def test_items_added_removed_and_reordered_are_audited(w):
    a, ws = w.actor, w.ws
    pack = packs.create_pack(w.meeting(), "P", workspace_id=ws, actor_principal_id=a)
    d1, d2 = w.document(), w.document()
    i1 = packs.add_pack_item(pack.id, d1, workspace_id=ws, actor_principal_id=a)
    i2 = packs.add_pack_item(pack.id, d2, workspace_id=ws, actor_principal_id=a)
    packs.reorder_pack_items(
        pack.id, [i2.id, i1.id], workspace_id=ws, clearance=RESTRICTED_CLEARANCE,
        actor_principal_id=a,
    )
    packs.remove_pack_item(i1.id, workspace_id=ws, actor_principal_id=a)

    events = w.events("board_pack", pack.id)
    assert _actions(events) == ["created", "item_added", "item_added", "item_removed", "reordered"]
    added = [e for e in events if e.action == "item_added"]
    assert {e.payload["document_id"] for e in added} == {d1, d2}
    reorder = next(e for e in events if e.action == "reordered")
    assert reorder.payload["ordered_item_ids"] == [i2.id, i1.id]
    removed = next(e for e in events if e.action == "item_removed")
    assert removed.payload["document_id"] == d1
    assert all(str(e.actor_principal_id) == a for e in events)


def test_supersede_records_the_old_pack_superseded_and_the_new_one_created(w):
    a, ws = w.actor, w.ws
    pack = packs.create_pack(w.meeting(), "v1", workspace_id=ws, actor_principal_id=a)
    packs.add_pack_item(pack.id, w.document(), workspace_id=ws, actor_principal_id=a)
    cur = packs.get_pack(pack.id, workspace_id=ws, clearance=RESTRICTED_CLEARANCE)
    pub = packs.publish_pack(
        pack.id, expected_version=cur.version, workspace_id=ws,
        clearance=RESTRICTED_CLEARANCE, actor_principal_id=a,
    )
    new, old = packs.supersede_pack(
        pack.id, "v2", expected_version=pub.version, workspace_id=ws,
        clearance=RESTRICTED_CLEARANCE, actor_principal_id=a,
    )

    old_ev = next(e for e in w.events("board_pack", old.id) if e.action == "superseded")
    assert old_ev.payload["replacement_id"] == new.id
    new_events = w.events("board_pack", new.id)
    assert _actions(new_events) == ["created"]
    assert new_events[0].payload["supersedes_id"] == old.id
    assert new_events[0].payload["version_no"] == 2
    assert new_events[0].payload["items_copied"] == 1


def test_a_refused_pack_write_records_nothing(w):
    a, ws = w.actor, w.ws
    pack = packs.create_pack(w.meeting(), "P", workspace_id=ws, actor_principal_id=a)
    published = packs.publish_pack(
        pack.id, expected_version=pack.version, workspace_id=ws,
        clearance=RESTRICTED_CLEARANCE, actor_principal_id=a,
    )
    before = len(w.all_events())

    with pytest.raises(StaleBoardPackError):
        packs.publish_pack(
            pack.id, expected_version=published.version + 99, workspace_id=ws,
            clearance=RESTRICTED_CLEARANCE, actor_principal_id=a,
        )
    with pytest.raises(BoardPackLockedError):  # a published pack is immutable
        packs.add_pack_item(pack.id, w.document(), workspace_id=ws, actor_principal_id=a)
    with pytest.raises(BoardPackLockedError):
        packs.reorder_pack_items(
            pack.id, [str(uuid.uuid4())], workspace_id=ws, clearance=RESTRICTED_CLEARANCE,
            actor_principal_id=a,
        )

    # A refused duplicate on a draft is not a change either.
    draft = packs.create_pack(w.meeting(), "D", workspace_id=ws, actor_principal_id=a)
    doc = w.document()
    packs.add_pack_item(draft.id, doc, workspace_id=ws, actor_principal_id=a)
    after_draft = len(w.all_events())
    with pytest.raises(packs.BoardPackValidationError):
        packs.add_pack_item(draft.id, doc, workspace_id=ws, actor_principal_id=a)

    assert len(w.all_events()) == after_draft
    # Only the draft's own create + its one successful add are new since `before`.
    assert after_draft == before + 2


def test_an_actor_outside_the_workspace_rolls_the_whole_mutation_back(w):
    """The audit is in the same transaction: a refused actor leaves no pack behind."""
    ws = w.ws
    stranger = str(uuid.uuid4())
    _admin(
        "INSERT INTO principal (id, name, role, clearance) VALUES (%s, 'Stranger', 'director', 3)",
        (stranger,),
    )
    try:
        meeting = w.meeting()
        with pytest.raises(audit.ActorNotInWorkspace):
            packs.create_pack(meeting, "Ghost", workspace_id=ws, actor_principal_id=stranger)
        assert packs.list_packs(meeting, workspace_id=ws, clearance=RESTRICTED_CLEARANCE) == []
        assert w.events("board_pack") == []
    finally:
        _admin("DELETE FROM principal WHERE id = %s", (stranger,))


def test_prep_publish_records_exactly_one_event_and_packs_publish_exactly_one(w):
    """Two publish paths, one event each — never two for a single publish."""
    a, ws = w.actor, w.ws

    via_packs = packs.create_pack(w.meeting(), "A", workspace_id=ws, actor_principal_id=a)
    packs.publish_pack(
        via_packs.id, expected_version=via_packs.version, workspace_id=ws,
        clearance=RESTRICTED_CLEARANCE, actor_principal_id=a,
    )
    assert _actions(w.events("board_pack", via_packs.id)).count("published") == 1

    m2 = w.meeting()
    via_prep = packs.create_pack(m2, "B", workspace_id=ws, actor_principal_id=a)
    prep.publish_preread(m2, workspace_id=ws, actor_id=a)
    assert _actions(w.events("board_pack", via_prep.id)).count("published") == 1


# --------------------------------------------------------------------- agenda


def test_agenda_create_update_delete_are_audited_with_the_actor(w):
    a, ws = w.actor, w.ws
    m = w.meeting()
    item = agenda.create_agenda_item(
        m, "Financials", workspace_id=ws, duration_minutes=20, presenter="CFO",
        description="private prose", actor_principal_id=a,
    )
    edited = agenda.update_agenda_item(
        item.id, expected_version=item.version, workspace_id=ws, duration_minutes=30,
        actor_principal_id=a,
    )
    agenda.delete_agenda_item(
        item.id, expected_version=edited.version, workspace_id=ws, actor_principal_id=a
    )

    events = w.events("agenda_item", item.id)
    assert _actions(events) == ["created", "deleted", "updated"]
    assert all(str(e.actor_principal_id) == a for e in events)
    upd = next(e for e in events if e.action == "updated")
    assert upd.payload["changed_fields"] == ["duration_minutes"]
    assert upd.payload["duration_minutes"] == 30
    created = next(e for e in events if e.action == "created")
    assert created.payload["title"] == "Financials"
    # Free text has no governance meaning and the trail cannot be corrected.
    assert not any("private prose" in str(e.payload) for e in events)


def test_agenda_reorder_is_one_event_on_the_meeting(w):
    a, ws = w.actor, w.ws
    m = w.meeting()
    x = agenda.create_agenda_item(m, "X", workspace_id=ws, actor_principal_id=a)
    y = agenda.create_agenda_item(m, "Y", workspace_id=ws, actor_principal_id=a)
    agenda.reorder_agenda_items(m, [y.id, x.id], workspace_id=ws, actor_principal_id=a)

    events = [e for e in w.events("meeting", m) if e.action == "reordered"]
    assert len(events) == 1
    assert events[0].payload == {"scope": "agenda", "ordered_item_ids": [y.id, x.id]}
    assert str(events[0].actor_principal_id) == a


def test_a_refused_agenda_write_records_nothing(w):
    a, ws = w.actor, w.ws
    m = w.meeting()
    item = agenda.create_agenda_item(m, "X", workspace_id=ws, actor_principal_id=a)
    before = len(w.all_events())

    with pytest.raises(StaleAgendaItemError):
        agenda.update_agenda_item(
            item.id, expected_version=item.version + 99, workspace_id=ws, title="Z",
            actor_principal_id=a,
        )
    with pytest.raises(StaleAgendaItemError):
        agenda.delete_agenda_item(
            item.id, expected_version=item.version + 99, workspace_id=ws, actor_principal_id=a
        )
    with pytest.raises(AgendaItemNotFound):
        agenda.delete_agenda_item(
            str(uuid.uuid4()), expected_version=1, workspace_id=ws, actor_principal_id=a
        )
    with pytest.raises(agenda.AgendaItemValidationError):
        agenda.reorder_agenda_items(m, [str(uuid.uuid4())], workspace_id=ws, actor_principal_id=a)

    assert len(w.all_events()) == before


def test_the_trail_is_tenant_isolated(w):
    other = _World()
    try:
        pack = packs.create_pack(
            w.meeting(), "P", workspace_id=w.ws, actor_principal_id=w.actor
        )
        assert len(w.events("board_pack", pack.id)) == 1
        assert other.events("board_pack", pack.id) == []
    finally:
        other.close()
