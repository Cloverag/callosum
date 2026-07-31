"""Read endpoints for meeting agendas (Meridian P3, CP-C — ADR-014).

Brought forward ahead of `meetings`, against the roadmap's original ordering. That
ordering assumed "nothing renders agenda alone", which the codebase disproves:
`meeting-detail` and the dashboard hero both render agenda items today, through the
`agenda` array the meetings mock invented. `Meeting` has no such field in the domain —
agenda is its own aggregate (CP2) — so agenda has to be real before meetings can stop
being a mock.

1:1 with `meridian/agenda.py`, minus `workspace_id` (ADR-013).

Writes follow the three CP-D rules set in `meetings.py`: session-derived identity,
`expected_version` on every mutation with 409 on mismatch, and PATCH keeping absent /
null / value distinct. Two things are specific to agenda:

**`DELETE` takes `expected_version` as a query parameter, not a body.** A delete is
still a mutation and still needs the concurrency check — deleting an item someone else
just rewrote is exactly the lost update the checkpoint exists to prevent. A request
body on `DELETE` is legal but poorly supported by proxies and clients, so the version
travels in the query string where it is unambiguous.

**`reorder` deliberately has no `expected_version`.** The domain takes the full ordered
list of item ids and rejects any set that is not exactly the meeting's items, so a
stale client is caught by the *content* of the request rather than by a counter — send
a list missing an item somebody just added and it is refused. Adding a version here
would be a second, weaker check on top of a total one.
"""

import uuid

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict

from meridian import agenda as domain
from meridian.api.deps import CurrentPrincipal

router = APIRouter(prefix="/api/agenda", tags=["agenda"])


class AgendaItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meeting_id: uuid.UUID
    title: str
    description: str | None = None
    #: `int` only, though the domain also accepts a numeric string for CLI callers.
    #: An API that accepts both has two ways to say one thing and a parser to keep.
    duration_minutes: int | None = None
    presenter: str | None = None
    position: int | None = None


class AgendaItemPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int
    title: str | None = None
    description: str | None = None
    duration_minutes: int | None = None
    presenter: str | None = None


class AgendaReorder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meeting_id: uuid.UUID
    ordered_item_ids: list[uuid.UUID]


@router.get("")
def list_agenda_items(meeting_id: uuid.UUID, principal: CurrentPrincipal) -> list[domain.AgendaItem]:
    """A meeting's agenda, ordered by `position ASC`.

    `meeting_id` is required rather than optional: an agenda item only means anything
    against the meeting it belongs to, and a workspace-wide list of every item across
    every meeting is not a question any surface asks.
    """
    return domain.list_agenda_items(str(meeting_id), workspace_id=principal.workspace_id)


@router.get("/{agenda_item_id}")
def get_agenda_item(agenda_item_id: uuid.UUID, principal: CurrentPrincipal) -> domain.AgendaItem:
    return domain.get_agenda_item(str(agenda_item_id), workspace_id=principal.workspace_id)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_agenda_item(body: AgendaItemCreate, principal: CurrentPrincipal) -> domain.AgendaItem:
    """Appends an item to a meeting's agenda.

    `position` is optional: omitted, the domain appends. Supplying one inserts at that
    position and shifts the rest, which is why it is a create argument rather than
    something to PATCH afterwards — an insert is a reordering of everything after it.
    """
    return domain.create_agenda_item(
        str(body.meeting_id),
        body.title,
        workspace_id=principal.workspace_id,
        description=body.description,
        duration_minutes=body.duration_minutes,
        presenter=body.presenter,
        position=body.position,
    )


@router.patch("/{agenda_item_id}")
def update_agenda_item(
    agenda_item_id: uuid.UUID, body: AgendaItemPatch, principal: CurrentPrincipal
) -> domain.AgendaItem:
    """Updates the fields that were sent, under optimistic concurrency.

    `position` is absent on purpose — moving an item is `reorder`, which sees the whole
    list. Patching one item's position would leave the others to be fixed up by whoever
    remembered.
    """
    changes = body.model_dump(exclude_unset=True)
    changes.pop("expected_version", None)
    return domain.update_agenda_item(
        str(agenda_item_id),
        expected_version=body.expected_version,
        workspace_id=principal.workspace_id,
        **changes,
    )


@router.delete("/{agenda_item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agenda_item(
    agenda_item_id: uuid.UUID, expected_version: int, principal: CurrentPrincipal
) -> None:
    """Removes an item and closes the gap in `position`.

    `expected_version` is required and is a query parameter — see the module docstring.
    Deleting an item somebody else just edited is a lost update like any other.
    """
    domain.delete_agenda_item(
        str(agenda_item_id),
        expected_version=expected_version,
        workspace_id=principal.workspace_id,
    )


@router.post("/reorder")
def reorder_agenda_items(
    body: AgendaReorder, principal: CurrentPrincipal
) -> list[domain.AgendaItem]:
    """Reorders a meeting's agenda by supplying its ids in the new order.

    Returns the whole agenda rather than an acknowledgement: after a reorder every
    item's `position` may have moved, so anything less would leave the caller to guess
    at the new state or re-fetch it.
    """
    return domain.reorder_agenda_items(
        str(body.meeting_id),
        [str(i) for i in body.ordered_item_ids],
        workspace_id=principal.workspace_id,
    )
