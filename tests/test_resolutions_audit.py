"""Resolution mutations leave an attributed, append-only trail (#168).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest tests/test_resolutions_audit.py``.

---------------------------------------------------------------------------
THE GAP, WHICH A COVERAGE COUNT UNDERSTATED
---------------------------------------------------------------------------
`meridian/resolutions.py` had 2 `record_audit_event` calls against 6 mutating routes.
Tracing each route to its domain function showed that was the better half of the story:

    create_resolution                NO audit
    update_resolution                NO audit
    record_vote                      audited, but ANONYMOUS
    transition_resolution            NO audit   <- how a motion is adopted or rejected
    supersede_resolution             NO audit
    bridge_resolution_to_commitment  audited, but ANONYMOUS

Neither existing call passed `actor_principal_id`, so **every resolution event this
module has ever written is unattributed**. For a vote that matters more than it looks:
the payload carries `board_member_id`, which is *whose vote it is*, not who submitted
it. A vote recorded on a member's behalf by someone else and one they cast themselves
are different events, and the trail could not distinguish them.

`cli.py`'s seeder is exempt from attribution (#166 — a bootstrap path has no
authenticated actor, and a fabricated one is worse than none). All six of these run
behind `CurrentPrincipal`; there was always a caller to name.

The DB-free half is `tests/test_resolutions_audit_static.py`.
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
from meridian import audit, board_members, decisions, meetings, resolutions
from meridian.resolutions import (
    ResolutionNotFound,
    ResolutionValidationError,
    StaleResolutionError,
)

pytestmark = pytest.mark.integration


def _admin(sql: str, params: tuple = ()) -> None:
    with psycopg.connect(settings().postgres_dsn) as conn:
        conn.execute(sql, params)
        conn.commit()


class _World:
    """A workspace, an actor with an active membership, a meeting and a decision."""

    def __init__(self) -> None:
        self.ws = str(uuid.uuid4())
        self.actor = str(uuid.uuid4())
        clearance = identity.ROLE_TO_CLEARANCE["director"]
        _admin(
            "INSERT INTO workspace (id, name, external_id) VALUES (%s, %s, %s)",
            (self.ws, f"res-{self.ws[:8]}", self.ws),
        )
        _admin(
            "INSERT INTO principal (id, name, role, clearance) VALUES (%s, %s, 'director', %s)",
            (self.actor, f"Res Actor {self.actor[:6]}", clearance),
        )
        _admin(
            "INSERT INTO membership (principal_id, workspace_id, role, clearance, active)"
            " VALUES (%s, %s, 'director', %s, true)",
            (self.actor, self.ws, clearance),
        )
        self.meeting = meetings.create_meeting("Audited Board Meeting", workspace_id=self.ws)
        self.decision = decisions.create_decision(
            self.meeting.id, "A decision to formalise", workspace_id=self.ws
        )

    def resolution(self, title: str = "Resolution 1", body: str = "RESOLVED THAT the budget passes."):
        return resolutions.create_resolution(
            self.decision.id, title, body,
            workspace_id=self.ws, actor_principal_id=self.actor,
        )

    def member(self) -> str:
        return board_members.create_member(
            "Director Vote", "director",
            workspace_id=self.ws, actor_principal_id=self.actor,
        ).id

    def events(self, aggregate_id: str | None = None) -> list:
        return audit.list_audit_events(
            aggregate_type="resolution", aggregate_id=aggregate_id, workspace_id=self.ws
        )

    def close(self) -> None:
        for table in ("audit_event", "resolution_vote", "resolution", "commitment",
                      "board_member", "decision", "agenda_item", "meeting", "membership"):
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


def _newest_first(events) -> list[str]:
    """Actions in the order `list_audit_events` returns them: **newest first**.

    `ORDER BY created_at DESC, id DESC`. Asserting the sequence rather than sorting it
    pins the reading order as part of the contract — `test_minutes_audit.py` learned
    this the hard way when four assertions went in backwards and CI caught them.
    """
    return [e.action for e in events]


# ----------------------------------------------- the four that wrote nothing


def test_create_is_audited_with_the_actor(w):
    r = w.resolution()
    events = w.events(r.id)
    assert _newest_first(events) == ["created"]
    assert str(events[0].actor_principal_id) == w.actor
    assert events[0].payload["status"] == "draft"
    assert events[0].payload["decision_id"] == w.decision.id


def test_update_is_audited_and_names_only_the_fields_that_moved(w):
    """`changed_fields` is derived from what the caller supplied, not from a literal.

    `update_resolution` takes `title` and `body` as independently optional, so a payload
    naming both when one moved would be a fabricated detail in an append-only trail.
    """
    r = w.resolution()
    resolutions.update_resolution(
        r.id, expected_version=r.version, body="RESOLVED THAT the budget passes, as amended.",
        workspace_id=w.ws, actor_principal_id=w.actor,
    )
    events = w.events(r.id)
    assert _newest_first(events) == ["updated", "created"]
    assert events[0].payload["changed_fields"] == ["body"], "title did not move"
    assert str(events[0].actor_principal_id) == w.actor


def test_transition_is_audited_and_names_the_status_it_left(w):
    """The most governance-critical mutation here, and the one that wrote nothing.

    This is how a motion becomes adopted or rejected. An adoption is not recoverable
    from the resulting row alone — `status = 'adopted'` does not say who adopted it.
    """
    r = w.resolution()
    adopted = resolutions.transition_resolution(
        r.id, resolutions.ADOPTED, expected_version=r.version,
        workspace_id=w.ws, actor_principal_id=w.actor,
    )
    assert adopted.status == "adopted"

    events = w.events(r.id)
    assert _newest_first(events) == ["status_changed", "created"]
    assert events[0].payload["from_status"] == "draft"
    assert events[0].payload["status"] == "adopted"
    assert str(events[0].actor_principal_id) == w.actor


def test_supersede_is_one_event_on_the_old_resolution(w):
    """One event, on the OLD id — as `documents` and `minutes` both do.

    The assertion that matters is the absence of a second event on the replacement: a
    `created` there would make an auditor filtering `action = 'created'` read amendments
    and original motions as the same kind of act.
    """
    r = w.resolution()
    adopted = resolutions.transition_resolution(
        r.id, resolutions.ADOPTED, expected_version=r.version,
        workspace_id=w.ws, actor_principal_id=w.actor,
    )
    new, old = resolutions.supersede_resolution(
        adopted.id, "Resolution 1 (amended)", "RESOLVED THAT the amended budget passes.",
        expected_version=adopted.version, workspace_id=w.ws, actor_principal_id=w.actor,
    )

    assert _newest_first(w.events(r.id)) == ["superseded", "status_changed", "created"]
    assert w.events(new.id) == [], "the replacement must not get its own created event"

    superseded = w.events(r.id)[0]
    assert superseded.payload["new_resolution_id"] == new.id
    assert superseded.payload["version_no"] == 1
    assert superseded.payload["new_version_no"] == 2


# -------------------------------------- the two that wrote, but anonymously


def test_a_vote_now_names_the_caller_as_well_as_the_member(w):
    """The defect this test exists for: `board_member_id` is the subject, not the actor.

    Both are needed. A vote cast by the member themselves and one recorded on their
    behalf are different events, and before this change the trail held only the subject.
    """
    r = w.resolution()
    member = w.member()
    resolutions.record_vote(
        r.id, member, resolutions.VOTE_FOR, workspace_id=w.ws, actor_principal_id=w.actor,
    )

    voted = [e for e in w.events(r.id) if e.action == "voted"]
    assert len(voted) == 1
    assert str(voted[0].actor_principal_id) == w.actor, "the caller"
    assert voted[0].payload["board_member_id"] == member, "the subject"
    assert voted[0].payload["vote"] == "for"


def test_the_commitment_bridge_now_names_the_caller(w):
    """The second pre-existing anonymous event.

    The action is left as `status_changed` with a `detail` discriminator, exactly as it
    was: it is a poor fit for an act that changes no status, but changing it would make
    old and new events for the same act disagree. Reported in the PR, not fixed here.
    """
    r = w.resolution()
    adopted = resolutions.transition_resolution(
        r.id, resolutions.ADOPTED, expected_version=r.version,
        workspace_id=w.ws, actor_principal_id=w.actor,
    )
    member = w.member()
    resolutions.bridge_resolution_to_commitment(
        adopted.id, member, workspace_id=w.ws, actor_principal_id=w.actor,
    )

    bridged = [
        e for e in w.events(r.id)
        if e.payload.get("detail") == "resolution_bridged_to_commitment"
    ]
    assert len(bridged) == 1
    assert str(bridged[0].actor_principal_id) == w.actor
    assert bridged[0].payload["commitment_id"]


# ------------------------------------------------------------------ refusals


def test_a_refused_resolution_write_records_nothing(w):
    """Four refusal branches, each a different point in the domain.

    `rules.md` §2: the trail records only events that happened. A write placed before
    the mutation would record three of these four as successes.
    """
    r = w.resolution()
    before = len(w.events())

    with pytest.raises(ResolutionNotFound):
        resolutions.update_resolution(
            str(uuid.uuid4()), expected_version=1, title="x",
            workspace_id=w.ws, actor_principal_id=w.actor,
        )

    with pytest.raises(StaleResolutionError):
        resolutions.update_resolution(
            r.id, expected_version=r.version + 99, title="x",
            workspace_id=w.ws, actor_principal_id=w.actor,
        )

    with pytest.raises(ResolutionValidationError):
        resolutions.update_resolution(
            r.id, expected_version=r.version, title="   ",
            workspace_id=w.ws, actor_principal_id=w.actor,
        )

    # An adopted resolution is immutable.
    adopted = resolutions.transition_resolution(
        r.id, resolutions.ADOPTED, expected_version=r.version,
        workspace_id=w.ws, actor_principal_id=w.actor,
    )
    with pytest.raises(ResolutionValidationError):
        resolutions.update_resolution(
            adopted.id, expected_version=adopted.version, title="too late",
            workspace_id=w.ws, actor_principal_id=w.actor,
        )

    # Only the one successful transition was recorded.
    assert len(w.events()) == before + 1


def test_an_actor_outside_the_workspace_rolls_the_whole_mutation_back(w):
    """What makes the audit write load-bearing rather than decorative.

    `record_audit_event` refuses an actor with no active membership, and because the
    write shares the mutation's transaction, the resolution goes with it. A caller
    cannot supply a bad actor and still get the mutation.
    """
    outsider = str(uuid.uuid4())
    _admin(
        "INSERT INTO principal (id, name, role, clearance) VALUES (%s, 'Outsider', 'observer', 0)",
        (outsider,),
    )
    try:
        with pytest.raises(audit.ActorNotInWorkspace):
            resolutions.create_resolution(
                w.decision.id, "Should not survive", "RESOLVED THAT nothing.",
                workspace_id=w.ws, actor_principal_id=outsider,
            )
        assert resolutions.list_resolutions(workspace_id=w.ws) == []
        assert w.events() == []
    finally:
        _admin("DELETE FROM principal WHERE id = %s", (outsider,))


# ------------------------------------------------------------------- payload


def test_the_payload_never_carries_the_motion_text(w):
    """The motion body stays out of the trail; its length goes in.

    Same reasoning as `minutes._audit_minutes` — D7 leaves the audit trail's own
    disclosure policy undecided, so the formal text does not get copied onto it. `title`
    IS carried, matching `packs._audit_pack`: it is the handle that says which motion an
    event is about.
    """
    import json

    secret = "RESOLVED THAT the CFO salary band moves to 185K."
    r = w.resolution("Compensation motion", secret)
    resolutions.transition_resolution(
        r.id, resolutions.ADOPTED, expected_version=r.version,
        workspace_id=w.ws, actor_principal_id=w.actor,
    )

    for event in w.events():
        blob = json.dumps(event.payload)
        assert "185K" not in blob and "salary band" not in blob
    created = [e for e in w.events(r.id) if e.action == "created"][0]
    assert created.payload["body_chars"] == len(secret)
    assert created.payload["title"] == "Compensation motion"
