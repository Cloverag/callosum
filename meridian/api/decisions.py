"""Read endpoints for decisions (Meridian P3, CP-C — ADR-014).

Follows `resolutions.py`, the CP-B slice, exactly: 1:1 with `meridian/decisions.py`
minus `workspace_id`, which comes from `deps.current_principal` and is refused as an
input by `tests/test_openapi_input_guard.py`.

**One shape difference from every other read module.** `list_decisions` takes
`meeting_id` as a *required* argument, not an optional filter — a decision only exists
in the context of a meeting, so there is no "all decisions in the workspace" query to
expose. It is therefore a required query parameter, and omitting it is a 422 rather
than an unscoped listing.

`status` stays optional, and an unknown value raises `DecisionValidationError` in the
domain, which `errors.install_exception_handlers` maps to 422 without this module
naming it.
"""

import uuid

from fastapi import APIRouter

from meridian import decisions as domain
from meridian.api.deps import CurrentPrincipal

router = APIRouter(prefix="/api/decisions", tags=["decisions"])


@router.get("")
def list_decisions(
    meeting_id: uuid.UUID,
    principal: CurrentPrincipal,
    status: str | None = None,
) -> list[domain.Decision]:
    """Decisions for one meeting, each with its director stances.

    The dataclass is returned as-is. Field names match `frontend/src/lib/decisions.ts`
    one for one, so a response model would only be a place for the two to drift.
    """
    return domain.list_decisions(
        str(meeting_id),
        workspace_id=principal.workspace_id,
        status=status,
    )


@router.get("/{decision_id}")
def get_decision(decision_id: uuid.UUID, principal: CurrentPrincipal) -> domain.Decision:
    """One decision with its stances.

    A decision in another workspace raises `DecisionNotFound`, because RLS means the row
    is not there to find rather than because this function checks. "Missing" and "exists
    but not yours" are deliberately the same answer.
    """
    return domain.get_decision(str(decision_id), workspace_id=principal.workspace_id)
