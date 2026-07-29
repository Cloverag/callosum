"""Read endpoints for board packs (Meridian P3, CP-C — ADR-014).

**The highest-risk read path in the codebase**, and the one place where the ADR-013
rule earns its keep twice over.

`list_packs` and `get_pack` take BOTH `workspace_id` and `clearance`. Neither is a
request parameter. `workspace_id` comes from the session as everywhere else; so does
`clearance`, via `deps.current_principal`, which resolves it from the caller's active
membership on every request. A client that could name its own clearance could read
every restricted document in the workspace — which is precisely what
`tests/test_openapi_input_guard.py` fails the build over.

Two contract properties travel through this endpoint unchanged, and the frontend tests
assert both against live data:

  - items are clearance-filtered and then RENUMBERED from 1, so a withheld item
    leaves no gap and no total to subtract from;
  - `position` is therefore a per-caller ordinal, not an identity.

Nothing here re-implements either. `_fetch_items_for_packs` does the filtering inside
the domain, and this endpoint returns what it produced.
"""

import uuid

from fastapi import APIRouter

from meridian import packs as domain
from meridian.api.deps import CurrentPrincipal

router = APIRouter(prefix="/api/packs", tags=["packs"])


@router.get("")
def list_packs(
    meeting_id: uuid.UUID,
    principal: CurrentPrincipal,
    status: str | None = None,
) -> list[domain.BoardPack]:
    """Board packs for a meeting, `version_no DESC, created_at DESC`.

    `meeting_id` is required: a pack is a pre-read *for a meeting*, and a
    workspace-wide list of every pack is not a question any surface asks.
    """
    return domain.list_packs(
        str(meeting_id),
        workspace_id=principal.workspace_id,
        status=status,
        clearance=principal.clearance,
    )


@router.get("/{pack_id}")
def get_pack(pack_id: uuid.UUID, principal: CurrentPrincipal) -> domain.BoardPack:
    return domain.get_pack(
        str(pack_id),
        workspace_id=principal.workspace_id,
        clearance=principal.clearance,
    )
