"""Minutes mutations leave an append-only trail (#168).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest tests/test_minutes_audit.py``.

---------------------------------------------------------------------------
THE GAP
---------------------------------------------------------------------------
At `51f499d`, `meridian/minutes.py` called `record_audit_event` **zero** times across
four mutating routes — the only domain module in the product with none. Minutes are the
formal record of what a board was told: they can be created, edited, frozen as final,
and corrected by supersession, and none of it named who did it.

Measured before writing these, per module, counting helper call sites rather than raw
`record_audit_event` greps (which undercount `packs.py`, where eight mutations share
`_audit_pack`):

    minutes        4 mutating routes   0 audit writes   <- this file
    resolutions    6                   2
    decisions      5                   1
    meetings       5                   2
    commitments    3                   1
    agenda/packs   11                  12  (P5 CP5A)

---------------------------------------------------------------------------
WHAT THESE PIN THAT A COVERAGE COUNT CANNOT
---------------------------------------------------------------------------
Four audit writes would satisfy any count. Three properties are what make them worth
having, and each has a test here because each has been got wrong in this repo before:

1. **A refused write records nothing.** All four refusal shapes — not found, stale
   version, locked because the minutes are final, and a parent meeting still in
   `draft` — must leave the trail empty. `rules.md` §2: the audit trail "records only
   events that happened". The notification dispatcher that recorded deliveries it never
   made is the incident behind that sentence.

2. **The body never enters the payload.** Minutes carry no `sensitivity` column
   (ADR-015), so there is no clearance predicate on an audit row to hold back a body it
   had copied, and who may read the audit trail is still undecided (D7). A payload
   carrying the prose would publish the board's record onto a surface whose disclosure
   policy does not exist yet.

3. **The route attributes the actor.** `actor_principal_id` is optional on the domain
   functions (the 26 pre-existing call sites predate the audit write, and `packs.py`
   made the same choice), so the signature does not force attribution. The test that
   the real HTTP path supplies it is what does.

The DB-free half of this is `tests/test_minutes_audit_static.py`.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip(
        "set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests",
        allow_module_level=True,
    )

import psycopg

from callosum import identity
from callosum.config import settings
from meridian import audit, meetings, minutes
from meridian.minutes import (
    MinutesLockedError,
    MinutesNotFound,
    MinutesValidationError,
    StaleMinutesError,
)

pytestmark = pytest.mark.integration


def _admin(sql: str, params: tuple = ()) -> None:
    with psycopg.connect(settings().postgres_dsn) as conn:
        conn.execute(sql, params)
        conn.commit()


class _World:
    """A workspace, an actor holding an active membership, and an in-progress meeting."""

    def __init__(self) -> None:
        self.ws = str(uuid.uuid4())
        self.actor = str(uuid.uuid4())
        clearance = identity.ROLE_TO_CLEARANCE["director"]
        _admin(
            "INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s)",
            (self.ws, f"min-{self.ws[:8]}", self.ws),
        )
        _admin(
            "INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, 'director', %s)",
            (self.actor, f"Minutes Actor {self.actor[:6]}", clearance),
        )
        # `record_audit_event` refuses an actor with no ACTIVE membership here, so the
        # membership is part of the fixture rather than something a test sets up.
        _admin(
            "INSERT INTO membership (principal_id, workspace_id, role, clearance, active)"
            " VALUES (%s, %s, 'director', %s, true)",
            (self.actor, self.ws, clearance),
        )

    def meeting(self, status: str = meetings.IN_PROGRESS) -> str:
        """A meeting walked to `status`. Minutes are locked on draft/scheduled/cancelled."""
        now = datetime.now(timezone.utc)
        m = meetings.create_meeting(
            "Audited Meeting",
            scheduled_start=now,
            scheduled_end=now + timedelta(hours=1),
            workspace_id=self.ws,
        )
        if status == meetings.DRAFT:
            return m.id
        m = meetings.transition_status(
            m.id, meetings.SCHEDULED, expected_version=1, workspace_id=self.ws
        )
        if status == meetings.SCHEDULED:
            return m.id
        m = meetings.transition_status(
            m.id, meetings.IN_PROGRESS, expected_version=2, workspace_id=self.ws
        )
        return m.id

    def draft(self, body: str = "Called to order at 10:00.") -> minutes.Minutes:
        return minutes.create_minutes(
            self.meeting(), body, workspace_id=self.ws, actor_principal_id=self.actor
        )

    def events(self, aggregate_id: str | None = None) -> list:
        return audit.list_audit_events(
            aggregate_type="minutes", aggregate_id=aggregate_id, workspace_id=self.ws
        )

    def close(self) -> None:
        for table in ("audit_event", "minutes", "agenda_item", "meeting", "membership"):
            _admin(f"DELETE FROM {table} WHERE workspace_id = %s", (self.ws,))
        _admin("DELETE FROM workspace WHERE id = %s", (self.ws,))
        _admin("DELETE FROM principal WHERE id = %s", (self.actor,))


def _newest_first(events) -> list[str]:
    """Actions in the order `list_audit_events` returns them: **newest first**.

    `audit.list_audit_events` is `ORDER BY created_at DESC, id DESC`. Asserting the
    sequence rather than `sorted(...)` — which is what `test_packs_agenda_audit.py`
    does — pins the reading order as part of the contract: a trail that silently
    flipped to oldest-first would still pass a sorted assertion, and any UI showing
    "most recent activity" would quietly invert.

    The first version of this file asserted oldest-first and CI caught all four. Kept
    as a helper so the direction is stated in one place.
    """
    return [e.action for e in events]


@pytest.fixture
def w():
    world = _World()
    try:
        yield world
    finally:
        world.close()


# ------------------------------------------------------------- one per mutation


def test_create_is_audited_with_the_actor(w):
    m = w.draft("Attendance noted.")

    events = w.events(m.id)
    assert [e.action for e in events] == ["created"]
    assert str(events[0].actor_principal_id) == w.actor
    assert events[0].payload["status"] == "draft"
    assert events[0].payload["version_no"] == 1


def test_update_is_audited_and_names_the_changed_field(w):
    m = w.draft()
    minutes.update_minutes(
        m.id,
        expected_version=m.version,
        body="Corrected attendance.",
        workspace_id=w.ws,
        actor_principal_id=w.actor,
    )

    events = w.events(m.id)
    assert _newest_first(events) == ["updated", "created"]
    assert events[0].payload["changed_fields"] == ["body"]
    assert str(events[0].actor_principal_id) == w.actor


def test_finalise_is_audited_as_a_status_change_naming_the_status_it_left(w):
    """`status_changed`, not `published` — see `finalise_minutes`'s docstring.

    `from_status` is in the payload because the resulting status alone cannot answer
    "was this frozen straight from draft, or re-finalised?", and a reader holding one
    event should not have to walk the whole trail to find out.
    """
    m = w.draft()
    final = minutes.finalise_minutes(
        m.id, expected_version=m.version, workspace_id=w.ws, actor_principal_id=w.actor
    )
    assert final.status == "final"

    events = w.events(m.id)
    assert _newest_first(events) == ["status_changed", "created"]
    assert events[0].payload["from_status"] == "draft"
    assert events[0].payload["status"] == "final"


def test_supersede_is_one_event_on_the_old_minutes_naming_the_replacement(w):
    """One event, on the OLD id — mirroring `documents.supersede_document`.

    The assertion that matters is the *absence* of a second event: a `created` on the
    new row would make an auditor filtering `action = 'created'` see corrections and
    originals as the same kind of act.
    """
    m = w.draft("First version.")
    final = minutes.finalise_minutes(
        m.id, expected_version=m.version, workspace_id=w.ws, actor_principal_id=w.actor
    )
    new, old = minutes.supersede_minutes(
        final.id,
        "Second version, corrected.",
        expected_version=final.version,
        workspace_id=w.ws,
        actor_principal_id=w.actor,
    )

    assert _newest_first(w.events(m.id)) == ["superseded", "status_changed", "created"]
    assert w.events(new.id) == [], "the replacement must not get its own created event"

    superseded = w.events(m.id)[0]
    assert superseded.payload["new_minutes_id"] == new.id
    assert superseded.payload["version_no"] == 1
    assert superseded.payload["new_version_no"] == 2


# ------------------------------------------------------------------- refusals


def test_a_refused_minutes_write_records_nothing(w):
    """All four refusal shapes. `rules.md` §2: only events that happened.

    Each is a different branch in the domain, and a write placed before the mutation
    instead of after would record three of these four as if they had succeeded.
    """
    m = w.draft()
    before = len(w.events())

    # 1. not found
    with pytest.raises(MinutesNotFound):
        minutes.update_minutes(
            str(uuid.uuid4()), expected_version=1, body="x",
            workspace_id=w.ws, actor_principal_id=w.actor,
        )

    # 2. stale version
    with pytest.raises(StaleMinutesError):
        minutes.update_minutes(
            m.id, expected_version=m.version + 99, body="x",
            workspace_id=w.ws, actor_principal_id=w.actor,
        )

    # 3. locked — finalised minutes are immutable
    final = minutes.finalise_minutes(
        m.id, expected_version=m.version, workspace_id=w.ws, actor_principal_id=w.actor
    )
    with pytest.raises(MinutesLockedError):
        minutes.update_minutes(
            final.id, expected_version=final.version, body="x",
            workspace_id=w.ws, actor_principal_id=w.actor,
        )

    # 4. a draft minutes cannot be superseded — only FINAL can
    second = w.draft("Another draft.")
    with pytest.raises(MinutesValidationError):
        minutes.supersede_minutes(
            second.id, "nope", expected_version=second.version,
            workspace_id=w.ws, actor_principal_id=w.actor,
        )

    # The only events added are the finalise in step 3 and the create in step 4.
    assert len(w.events()) == before + 2


def test_minutes_on_a_draft_meeting_are_refused_and_record_nothing(w):
    """The parent-meeting guard, which is the one refusal that fires before any row exists."""
    draft_meeting = w.meeting(meetings.DRAFT)
    with pytest.raises(MinutesLockedError):
        minutes.create_minutes(
            draft_meeting, "Too early.", workspace_id=w.ws, actor_principal_id=w.actor
        )
    assert w.events() == []


def test_an_actor_outside_the_workspace_rolls_the_whole_mutation_back(w):
    """`record_audit_event` refuses an actor with no active membership, and because the
    write shares the mutation's transaction the minutes row goes with it.

    This is the property that makes the audit write load-bearing rather than
    decorative: it cannot be skipped by a caller who supplies a bad actor and still
    get the mutation.
    """
    outsider = str(uuid.uuid4())
    _admin(
        "INSERT INTO principal (id, name, role, clearance) VALUES (%s, 'Outsider', 'observer', 0)",
        (outsider,),
    )
    meeting = w.meeting()
    try:
        with pytest.raises(audit.ActorNotInWorkspace):
            minutes.create_minutes(
                meeting, "Should not survive.", workspace_id=w.ws, actor_principal_id=outsider
            )
        assert minutes.list_minutes(meeting, workspace_id=w.ws) == []
        assert w.events() == []
    finally:
        _admin("DELETE FROM principal WHERE id = %s", (outsider,))


# --------------------------------------------------------------- the payload


def test_the_payload_never_carries_the_minutes_body(w):
    """ADR-015 + D7. See `_audit_minutes`'s docstring for the argument.

    Checked against the whole serialised payload, not against a `body` key, because the
    failure this guards is somebody adding the prose under any name at all.
    """
    secret = "RESOLVED: the CFO salary band moves to 185K."
    m = w.draft(secret)
    final = minutes.finalise_minutes(
        m.id, expected_version=m.version, workspace_id=w.ws, actor_principal_id=w.actor
    )
    minutes.supersede_minutes(
        final.id, "RESOLVED: corrected to 190K.",
        expected_version=final.version, workspace_id=w.ws, actor_principal_id=w.actor,
    )

    import json

    for event in w.events():
        blob = json.dumps(event.payload)
        assert "185K" not in blob and "190K" not in blob
        assert "CFO" not in blob and "RESOLVED" not in blob

    created = w.events(m.id)[0]
    assert created.payload["body_chars"] == len(secret), "the length is carried, the text is not"


# ----------------------------------------------------------------- the route


def test_the_route_attributes_every_minutes_event(w, monkeypatch):
    """The signature makes the actor optional; this is what makes the real path supply it.

    Driven through the FastAPI layer with a real session, because the defect it guards
    is a route that forgets to pass `actor_principal_id` — which a domain-level test
    cannot see, since it passes the actor itself.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from meridian.api import deps, errors
    from meridian.api import minutes as minutes_api
    from callosum.retrieve import Principal

    app = FastAPI()
    app.include_router(minutes_api.router)
    errors.install_exception_handlers(app)
    app.dependency_overrides[deps.current_principal] = lambda: Principal(
        id=w.actor, name="Minutes Actor", role="director",
        clearance=identity.ROLE_TO_CLEARANCE["director"], workspace_id=w.ws,
    )
    client = TestClient(app)
    meeting = w.meeting()

    created = client.post("/api/minutes", json={"meeting_id": meeting, "body": "Via the route."})
    assert created.status_code == 201, created.text
    mid = created.json()["id"]
    version = created.json()["version"]

    patched = client.patch(
        f"/api/minutes/{mid}", json={"expected_version": version, "body": "Edited via the route."}
    )
    assert patched.status_code == 200, patched.text

    finalised = client.post(
        f"/api/minutes/{mid}/finalise", json={"expected_version": patched.json()["version"]}
    )
    assert finalised.status_code == 200, finalised.text

    superseded = client.post(
        f"/api/minutes/{mid}/supersede",
        json={"expected_version": finalised.json()["version"], "new_body": "Corrected via route."},
    )
    assert superseded.status_code == 201, superseded.text

    events = w.events(mid)
    assert _newest_first(events) == ["superseded", "status_changed", "updated", "created"]
    assert {str(e.actor_principal_id) for e in events} == {w.actor}, (
        "every event from the HTTP path must name the caller — an unattributed event is "
        "the failure this test exists for"
    )
