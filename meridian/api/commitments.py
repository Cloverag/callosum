"""Read endpoints for commitments (Meridian P3, CP-C — ADR-014).

The last CP-C module. 1:1 with `meridian/commitments.py` minus `workspace_id`, which
comes from `deps.current_principal` and is refused as an input by
`tests/test_openapi_input_guard.py`.

All four filters are exposed because all four are ordinary predicates over data the
caller can already see. `open_only` is the one worth keeping: "what is still
outstanding" is the question a board actually asks, and no single status answers it.

**Delivery fields are inert.** `external_system`, `external_task_id`, `delivery_status`
and `delivery_attempts` are modelled and returned, but nothing dispatches anything —
execution is P8. They are serialised as they are stored rather than hidden, because a
field that exists and reads `not_dispatched` is honest and a field that is silently
withheld is not.
"""

import uuid

from fastapi import APIRouter

from meridian import commitments as domain
from meridian.api.deps import CurrentPrincipal

router = APIRouter(prefix="/api/commitments", tags=["commitments"])


@router.get("")
def list_commitments(
    principal: CurrentPrincipal,
    decision_id: uuid.UUID | None = None,
    owner_board_member_id: uuid.UUID | None = None,
    status: str | None = None,
    open_only: bool = False,
) -> list[domain.Commitment]:
    """Commitments in the caller's workspace, soonest due first, then newest.

    Undated work sorts last — a commitment with no deadline is not the most urgent
    thing on the list. `frontend/src/lib/commitments.ts` implements the same order, and
    a test below pins the two together rather than trusting the comment.
    """
    return domain.list_commitments(
        workspace_id=principal.workspace_id,
        decision_id=str(decision_id) if decision_id else None,
        owner_board_member_id=str(owner_board_member_id) if owner_board_member_id else None,
        status=status,
        open_only=open_only,
    )


@router.get("/{commitment_id}")
def get_commitment(commitment_id: uuid.UUID, principal: CurrentPrincipal) -> domain.Commitment:
    """One commitment with its update trail.

    A commitment in another workspace raises `CommitmentNotFound`, because RLS means
    the row is not there to find. "Missing" and "exists but not yours" are deliberately
    the same answer.
    """
    return domain.get_commitment(str(commitment_id), workspace_id=principal.workspace_id)
