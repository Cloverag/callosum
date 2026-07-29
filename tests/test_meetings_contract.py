"""The frontend's meeting statuses must be the domain's (issue #47).

Fast suite — no database, no server. It reads `frontend/src/lib/meetings.ts` and
compares it to `meridian/meetings.py`.

This is the same technique the wire-shape tests use for resolutions and board members,
applied to an enum rather than a field set. It exists because the drift it catches was
real and lived for weeks: the type declared `review` and `archived`, which
`transition_status` would reject so no meeting could ever reach them, and omitted
`cancelled`, which the domain does have.

The omission was the dangerous half. `packs.py` locks on
`{in_progress, completed, cancelled}` and `minutes.py` on
`{draft, scheduled, cancelled}` — anything deriving a lock rule from the TypeScript
type would have dropped `cancelled` and concluded a cancelled meeting's pack was still
editable. `packs.ts` and `minutes.ts` sidestepped it by declaring their own lock sets;
this test removes the need for anyone to remember to do that again.
"""

import re
from pathlib import Path

import pytest

from meridian import meetings

TS_SOURCE = Path("frontend/src/lib/meetings.ts")


def _ts_statuses() -> set[str]:
    """The union members of `export type MeetingStatus`."""
    source = TS_SOURCE.read_text()
    block = re.search(r"export type MeetingStatus =(.*?);", source, re.S)
    assert block, "MeetingStatus not found in lib/meetings.ts"
    return set(re.findall(r'"(\w+)"', block.group(1)))


def _ts_record_keys(name: str) -> set[str]:
    """The keys of a `Record<MeetingStatus, …>` constant."""
    source = TS_SOURCE.read_text()
    block = re.search(rf"export const {name}: Record<MeetingStatus, [^>]+> = \{{(.*?)\n\}};", source, re.S)
    assert block, f"{name} not found in lib/meetings.ts"
    return set(re.findall(r"^\s{2}(\w+):", block.group(1), re.M))


def test_the_typescript_statuses_are_exactly_the_domain_statuses():
    domain = set(meetings._TRANSITIONS.keys())
    assert _ts_statuses() == domain, (
        "lib/meetings.ts and meridian/meetings.py disagree about the meeting lifecycle"
    )


def test_the_domain_has_no_review_or_archived_state():
    """Guards the specific phantoms #47 was filed for.

    They came from the PRD's prose lifecycle rather than from the state machine, which
    is how a document's description of a product ends up asserted as its behaviour.
    """
    domain = set(meetings._TRANSITIONS.keys())
    assert "review" not in domain
    assert "archived" not in domain
    assert "cancelled" in domain


@pytest.mark.parametrize(
    "constant", ["MEETING_STATUS_LABEL", "MEETING_STATUS_TONE", "MEETING_STATUS_DOT"]
)
def test_every_status_map_covers_exactly_the_domain(constant):
    # TypeScript's Record<MeetingStatus, …> already enforces completeness at compile
    # time. This catches the other direction: a map carrying a key the domain dropped,
    # which would typecheck only because the *type* was also wrong.
    assert _ts_record_keys(constant) == set(meetings._TRANSITIONS.keys())


def test_the_lock_sets_that_worked_around_this_still_include_cancelled():
    """`packs` and `minutes` declared their own lock sets to avoid the bad type.

    Now that the type is right they could bind to it, but the assertion belongs here
    either way — a lock rule that silently dropped `cancelled` would leave a cancelled
    meeting's pack editable, which is the concrete harm #47 described.
    """
    from meridian import minutes, packs

    assert "cancelled" in packs._LOCKED_MEETING_STATUSES
    assert "cancelled" in minutes._LOCKED_MEETING_STATUSES
