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

import datetime as dt
import uuid

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict

from meridian import commitments as domain
from meridian.api.deps import CurrentPrincipal


class CommitmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: uuid.UUID
    title: str
    owner_board_member_id: uuid.UUID
    resolution_id: uuid.UUID | None = None
    accountable_team: str | None = None
    detail: str | None = None
    #: A calendar day, not an instant. `date` rather than `datetime` so a client cannot
    #: smuggle a timezone into a deadline and have it land on the wrong day.
    due_date: dt.date | None = None


class CommitmentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int
    title: str | None = None
    detail: str | None = None
    due_date: dt.date | None = None
    accountable_team: str | None = None
    owner_board_member_id: uuid.UUID | None = None


class CommitmentUpdateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str
    expected_version: int
    new_status: str | None = None
    author_board_member_id: uuid.UUID | None = None

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


@router.post("", status_code=status.HTTP_201_CREATED)
def create_commitment(payload: CommitmentCreate, principal: CurrentPrincipal) -> domain.Commitment:
    """Records who owes what, arising from a decision.

    `owner_board_member_id` is required and must be an **active** member — an owner who
    has left the board is not an owner, and the domain checks rather than accepting a
    dangling reference.
    """
    return domain.create_commitment(
        str(payload.decision_id),
        payload.title,
        str(payload.owner_board_member_id),
        workspace_id=principal.workspace_id,
        resolution_id=str(payload.resolution_id) if payload.resolution_id else None,
        accountable_team=payload.accountable_team,
        detail=payload.detail,
        due_date=payload.due_date,
    )


@router.patch("/{commitment_id}")
def update_commitment(
    commitment_id: uuid.UUID, payload: CommitmentPatch, principal: CurrentPrincipal
) -> domain.Commitment:
    """Edits a commitment under optimistic concurrency.

    Status is not here — it moves through `record_update`, which requires a note. A
    status change with no reason is exactly the audit hole that design avoids.
    """
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("expected_version", None)
    if changes.get("owner_board_member_id") is not None:
        changes["owner_board_member_id"] = str(changes["owner_board_member_id"])
    return domain.update_commitment(
        str(commitment_id),
        expected_version=payload.expected_version,
        workspace_id=principal.workspace_id,
        **changes,
    )


@router.post("/{commitment_id}/updates", status_code=status.HTTP_201_CREATED)
def record_update(
    commitment_id: uuid.UUID, payload: CommitmentUpdateRecord, principal: CurrentPrincipal
) -> domain.Commitment:
    """Reports progress, optionally moving the status.

    **The note is required even when the status does not change.** A commitment's value
    is the trail of what happened to it, and an update with no reason is a row that says
    nothing.

    Returns the whole commitment rather than the update, because the status and version
    may both have moved and the caller needs the new numbers.
    """
    return domain.record_update(
        str(commitment_id),
        payload.note,
        expected_version=payload.expected_version,
        workspace_id=principal.workspace_id,
        new_status=payload.new_status,
        author_board_member_id=str(payload.author_board_member_id)
        if payload.author_board_member_id
        else None,
    )
