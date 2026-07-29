"""Read endpoints for meetings (Meridian P3, CP-C — ADR-014).

1:1 with `meridian/meetings.py`, minus `workspace_id` (ADR-013).

Landed after `agenda` deliberately. `Meeting` carries no agenda in the domain, and
until agenda had its own endpoint the surfaces that render one had nothing to fetch
from — so swapping meetings first would have meant deleting an agenda list with no
replacement.
"""

from fastapi import APIRouter

from meridian import meetings as domain
from meridian.api.deps import CurrentPrincipal

router = APIRouter(prefix="/api/meetings", tags=["meetings"])


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
def get_meeting(meeting_id: str, principal: CurrentPrincipal) -> domain.Meeting:
    return domain.get_meeting(meeting_id, workspace_id=principal.workspace_id)
