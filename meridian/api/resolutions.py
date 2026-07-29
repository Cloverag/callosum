"""Read endpoints for resolutions (Meridian P3, CP-B — ADR-014).

The first vertical slice: one aggregate, end to end, so the pattern every other module
follows is established once and reviewed once.

**1:1 with `meridian/resolutions.py`, minus one argument.** `list_resolutions` and
`get_resolution` both take `workspace_id`; neither endpoint accepts it. It comes from
`deps.current_principal`, which re-derives it from the session on every request — and
`tests/test_openapi_input_guard.py` fails the build if it ever appears in the schema.

`decision_id` and `status` *are* accepted, because they are ordinary filters over data
the caller can already see. The distinction is not "is it a parameter" but "does it
decide what you are allowed to read": `workspace_id` does, these do not.

**No error handling here.** Domain exceptions propagate and are mapped centrally by
`errors.install_exception_handlers`. A `ResolutionNotFound` becomes 404 and a
`ResolutionValidationError` — raised by `list_resolutions` for an unknown status —
becomes 422, without this module restating either.
"""

import uuid
from typing import Literal

from fastapi import APIRouter

from meridian import resolutions as domain
from meridian.api.deps import CurrentPrincipal

router = APIRouter(prefix="/api/resolutions", tags=["resolutions"])

@router.get("")
def list_resolutions(
    principal: CurrentPrincipal,
    decision_id: uuid.UUID | None = None,
    status: str | None = None,
) -> list[domain.Resolution]:
    """Resolutions in the caller's workspace, `version_no DESC, created_at DESC`.

    The dataclass is returned as-is rather than remapped through a response model.
    Field names already match `frontend/src/lib/resolutions.ts` one for one — that was
    the point of writing the mock against the Python contract — so a translation layer
    would only be somewhere for the two to drift apart.
    """
    return domain.list_resolutions(
        workspace_id=principal.workspace_id,
        decision_id=str(decision_id) if decision_id else None,
        status=status,
    )


@router.get("/{resolution_id}")
def get_resolution(resolution_id: uuid.UUID, principal: CurrentPrincipal) -> domain.Resolution:
    """One resolution with its votes.

    A resolution in another workspace raises `ResolutionNotFound` — not because this
    function checks, but because the RLS predicate means the row is not there to find.
    404 and "exists but not yours" are the same answer, which is the intent.
    """
    return domain.get_resolution(str(resolution_id), workspace_id=principal.workspace_id)
