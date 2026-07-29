"""Read endpoints for meeting agendas (Meridian P3, CP-C — ADR-014).

Brought forward ahead of `meetings`, against the roadmap's original ordering. That
ordering assumed "nothing renders agenda alone", which the codebase disproves:
`meeting-detail` and the dashboard hero both render agenda items today, through the
`agenda` array the meetings mock invented. `Meeting` has no such field in the domain —
agenda is its own aggregate (CP2) — so agenda has to be real before meetings can stop
being a mock.

1:1 with `meridian/agenda.py`, minus `workspace_id` (ADR-013).
"""

import uuid

from fastapi import APIRouter

from meridian import agenda as domain
from meridian.api.deps import CurrentPrincipal

router = APIRouter(prefix="/api/agenda", tags=["agenda"])


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
