"""Meeting endpoints (Meridian P3, CP-C reads · CP-D writes — ADR-014).

1:1 with `meridian/meetings.py`, minus `workspace_id` (ADR-013).

Landed after `agenda` deliberately. `Meeting` carries no agenda in the domain, and
until agenda had its own endpoint the surfaces that render one had nothing to fetch
from — so swapping meetings first would have meant deleting an agenda list with no
replacement.

---------------------------------------------------------------------------
CP-D — THE THREE RULES THE REST OF THE WRITES FOLLOW
---------------------------------------------------------------------------
**1. `created_by` comes from the session, never the body.** It is a
`UUID REFERENCES principal(id)` — an authorship claim. A client-supplied author is a
forgeable one, and ADR-013's reasoning about `workspace_id` applies unchanged: an
identity the request can choose is not an identity. It is therefore absent from
`MeetingCreate` entirely rather than accepted-and-ignored, so the OpenAPI guard can
see that it is not an input.

**2. `expected_version` is required on every mutation, and a mismatch is 409.**
Nothing here raises it — the domain does, and `errors.classify` already maps `Stale*`
to 409 by suffix. The endpoint's only job is to pass the caller's version through
unchanged.

**3. PATCH keeps absent, null and value distinct.** `scheduled_start`, `scheduled_end`
and `location` are all nullable, so `null` means *clear this field* and absent means
*leave it alone*. The domain already models exactly that with its `_UNSET` sentinel, so
the endpoint uses `model_dump(exclude_unset=True)` and lets a field that was never sent
simply not appear in the call. Collapsing the two — the obvious shortcut, where `None`
means "no change" — would make it impossible to clear a location once set.
"""

import datetime as dt
import uuid

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict

from meridian import meetings as domain
from meridian.api.deps import CurrentPrincipal

router = APIRouter(prefix="/api/meetings", tags=["meetings"])


class MeetingCreate(BaseModel):
    """Body for `POST /api/meetings`.

    No `created_by`, no `workspace_id`, no `status`: the first two come from the
    session and the third is always `draft` at creation, decided by the domain.
    """

    model_config = ConfigDict(extra="forbid")

    title: str
    scheduled_start: dt.datetime | None = None
    scheduled_end: dt.datetime | None = None
    location: str | None = None
    importance: str = domain.ROUTINE_IMPORTANCE


class MeetingPatch(BaseModel):
    """Body for `PATCH /api/meetings/{id}`.

    Every field except `expected_version` is optional *and* nullable, which is the
    tri-state rule above: omit to leave alone, send `null` to clear, send a value to
    set. `title` is the exception — it is `NOT NULL` in the schema, so a `null` is
    refused here rather than travelling to the domain to be refused there.

    Status is deliberately not patchable. It moves through `transition_status`, which
    enforces the state machine; allowing it here would be a second way to change it
    that skips the machine.
    """

    model_config = ConfigDict(extra="forbid")

    expected_version: int
    title: str | None = None
    scheduled_start: dt.datetime | None = None
    scheduled_end: dt.datetime | None = None
    location: str | None = None
    importance: str | None = None


class MeetingTransition(BaseModel):
    """Body for `POST /api/meetings/{id}/transition`."""

    model_config = ConfigDict(extra="forbid")

    new_status: str
    expected_version: int


@router.get("")
def list_meetings(principal: CurrentPrincipal, status: str | None = None) -> list[domain.Meeting]:
    """Meetings in the caller's workspace, calendar-ordered.

    Includes meetings with no scheduled window — a `draft` has none until it is
    scheduled. Filtering them out here would hide real records from the meetings list
    to suit the calendar, which is the calendar's problem to solve rather than this
    endpoint's.
    """
    return domain.list_meetings(workspace_id=principal.workspace_id, status=status)


@router.get("/{meeting_id}")
def get_meeting(meeting_id: uuid.UUID, principal: CurrentPrincipal) -> domain.Meeting:
    return domain.get_meeting(str(meeting_id), workspace_id=principal.workspace_id)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_meeting(body: MeetingCreate, principal: CurrentPrincipal) -> domain.Meeting:
    """Creates a `draft` meeting owned by the caller.

    `created_by` is the session principal. A caller cannot record someone else as the
    author, because there is nowhere in the request to say so.
    """
    return domain.create_meeting(
        body.title,
        workspace_id=principal.workspace_id,
        scheduled_start=body.scheduled_start,
        scheduled_end=body.scheduled_end,
        location=body.location,
        created_by=str(principal.id) if principal.id else None,
    )


@router.patch("/{meeting_id}")
def update_meeting(
    meeting_id: uuid.UUID, body: MeetingPatch, principal: CurrentPrincipal
) -> domain.Meeting:
    """Updates the fields that were sent, under optimistic concurrency.

    `exclude_unset=True` is what preserves the tri-state: a field the client never
    mentioned is not in `changes`, so the domain's `_UNSET` default stands and the
    column is untouched. A field sent as `null` *is* in `changes`, and clears it.

    A version mismatch raises `StaleMeetingError` in the domain, which arrives as 409
    without this function naming it.
    """
    changes = body.model_dump(exclude_unset=True)
    changes.pop("expected_version", None)
    return domain.update_meeting(
        str(meeting_id),
        expected_version=body.expected_version,
        workspace_id=principal.workspace_id,
        **changes,
    )


@router.post("/{meeting_id}/transition")
def transition_meeting(
    meeting_id: uuid.UUID, body: MeetingTransition, principal: CurrentPrincipal
) -> domain.Meeting:
    """Moves a meeting through its state machine.

    Separate from PATCH on purpose: the legal moves are a property of the domain, and
    an `InvalidTransition` is a 409 rather than a 422 because the request was
    well-formed and the *state* refused it — the same distinction a stale version
    draws.
    """
    return domain.transition_status(
        str(meeting_id),
        body.new_status,
        expected_version=body.expected_version,
        workspace_id=principal.workspace_id,
    )


# ---------------------------------------------------------------------------
# Material — documents assigned to this meeting (P4, ADR-018)
# ---------------------------------------------------------------------------

class MaterialAssign(BaseModel):
    """Body for `POST /api/meetings/{id}/material`.

    One field. `assigned_by` is deliberately absent for the same reason `created_by` is
    absent from `MeetingCreate` — it is an attribution, and an attribution the request
    can choose is not one. It comes from the session.
    """

    model_config = ConfigDict(extra="forbid")

    document_id: uuid.UUID


@router.get("/{meeting_id}/material")
def get_meeting_material(
    meeting_id: uuid.UUID, principal: CurrentPrincipal
) -> domain.MeetingMaterial:
    """Material for one meeting: what this caller may read, and how many they may not.

    `withheld` is a count and nothing else (ADR-018). It is disclosed rather than erased
    because this list claims to be *the material for this meeting*, and a director who
    prepares from a silently truncated one walks in believing they are prepared.

    `clearance` comes from `deps.current_principal`, re-derived from the caller's active
    membership on every request. It is not a parameter, and
    `tests/test_openapi_input_guard.py` fails the build if it becomes one.
    """
    return domain.meeting_material(
        str(meeting_id),
        workspace_id=principal.workspace_id,
        clearance=principal.clearance,
    )


@router.post("/{meeting_id}/material", status_code=status.HTTP_201_CREATED)
def assign_meeting_material(
    meeting_id: uuid.UUID, body: MaterialAssign, principal: CurrentPrincipal
) -> domain.MeetingMaterial:
    """Assigns a document to this meeting as material.

    **404 when either the meeting or the document is invisible to the caller**, with no
    way to tell which. The domain raises one exception type for both, deliberately: a
    403 here would confirm that a document exists at a clearance the caller cannot read,
    and document ids are derivable from candidate plaintext.

    Returns the material list rather than the created row. The caller's next question is
    always "what is on this meeting now", the answer is already clearance-filtered, and
    returning the row would mean the client either re-fetches or assembles a list the
    server could have given it correctly.
    """
    domain.assign_material(
        str(meeting_id),
        str(body.document_id),
        workspace_id=principal.workspace_id,
        clearance=principal.clearance,
        actor_principal_id=str(principal.id) if principal.id else None,
        assigned_by=str(principal.id) if principal.id else None,
    )
    return domain.meeting_material(
        str(meeting_id),
        workspace_id=principal.workspace_id,
        clearance=principal.clearance,
    )


@router.delete("/{meeting_id}/material/{document_id}")
def unassign_meeting_material(
    meeting_id: uuid.UUID, document_id: uuid.UUID, principal: CurrentPrincipal
) -> domain.MeetingMaterial:
    """Removes a document from this meeting's material.

    404 when the document is not assigned *or* is above the caller's clearance — one
    answer for both, so this is not a way to probe what a meeting holds.

    Returns the remaining material rather than 204, for the reason given on the POST:
    the response is the caller's next read, already filtered.
    """
    domain.unassign_material(
        str(meeting_id),
        str(document_id),
        workspace_id=principal.workspace_id,
        clearance=principal.clearance,
        actor_principal_id=str(principal.id) if principal.id else None,
    )
    return domain.meeting_material(
        str(meeting_id),
        workspace_id=principal.workspace_id,
        clearance=principal.clearance,
    )
