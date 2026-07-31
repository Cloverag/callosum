"""Decision endpoints (Meridian P3, CP-C reads · CP-D writes — ADR-014).

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

Writes follow the three CP-D rules set in `meetings.py`. Two things are specific here:

**`record_stance` has no `expected_version`.** It does not mutate the decision — it
upserts a row in `decision_stance` keyed on `(decision_id, person_name)`, so two
directors recording stances concurrently do not contend. What it *does* check is the
decision's status: stances may only be recorded while a decision is `proposed`, which
is the guard added in review of #22. A stance on an approved decision is 409, because
the decision's state refused it.

**`supersede` returns two decisions, so it returns an object rather than one of them.**
The old decision becomes `superseded` and a new one is created; a caller needs both,
and picking one to return would make the other something to go and look up.
"""

import uuid

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict

from meridian import decisions as domain
from meridian.api.deps import CurrentPrincipal

router = APIRouter(prefix="/api/decisions", tags=["decisions"])


class DecisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meeting_id: uuid.UUID
    title: str
    agenda_item_id: uuid.UUID | None = None
    rationale: str | None = None


class DecisionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int
    title: str | None = None
    rationale: str | None = None


class StanceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    person_name: str
    stance: str
    comment: str | None = None


class DecisionTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_status: str
    expected_version: int


class DecisionSupersede(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_title: str
    expected_version: int
    agenda_item_id: uuid.UUID | None = None
    rationale: str | None = None


class Supersession(BaseModel):
    """Both halves of a supersession — the caller needs each."""

    superseded: domain.Decision
    replacement: domain.Decision


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


@router.post("", status_code=status.HTTP_201_CREATED)
def create_decision(body: DecisionCreate, principal: CurrentPrincipal) -> domain.Decision:
    """Records a `proposed` decision against a meeting.

    `agenda_item_id` is optional and, when given, must belong to the same meeting — the
    domain checks, so a mismatched pair is a 422 rather than a silently orphaned link.
    """
    return domain.create_decision(
        str(body.meeting_id),
        body.title,
        workspace_id=principal.workspace_id,
        agenda_item_id=str(body.agenda_item_id) if body.agenda_item_id else None,
        rationale=body.rationale,
    )


@router.patch("/{decision_id}")
def update_decision(
    decision_id: uuid.UUID, body: DecisionPatch, principal: CurrentPrincipal
) -> domain.Decision:
    """Updates title and rationale under optimistic concurrency.

    `rationale` is nullable, so sending `null` clears it — the tri-state rule. Status is
    not here; it moves through `transition`.
    """
    changes = body.model_dump(exclude_unset=True)
    changes.pop("expected_version", None)
    return domain.update_decision(
        str(decision_id),
        expected_version=body.expected_version,
        workspace_id=principal.workspace_id,
        **changes,
    )


@router.post("/{decision_id}/stance", status_code=status.HTTP_201_CREATED)
def record_stance(
    decision_id: uuid.UUID, body: StanceRecord, principal: CurrentPrincipal
) -> domain.DecisionStance:
    """Records or changes one director's stance.

    No `expected_version`: this writes `decision_stance`, not the decision, and the
    upsert is keyed on `(decision_id, person_name)` so two directors voting at once do
    not contend. The guard that does apply is the decision's status — see the module
    docstring.
    """
    return domain.record_stance(
        str(decision_id),
        body.person_name,
        body.stance,
        workspace_id=principal.workspace_id,
        comment=body.comment,
    )


@router.post("/{decision_id}/transition")
def transition_decision(
    decision_id: uuid.UUID, body: DecisionTransition, principal: CurrentPrincipal
) -> domain.Decision:
    """Moves a decision through its lifecycle.

    `deferred` is terminal in this domain — a deferred decision cannot be re-proposed.
    That is a recorded product decision, not an oversight; see the review of #22.
    """
    return domain.transition_decision_status(
        str(decision_id),
        body.new_status,
        expected_version=body.expected_version,
        workspace_id=principal.workspace_id,
    )


@router.post("/{decision_id}/supersede", status_code=status.HTTP_201_CREATED)
def supersede_decision(
    decision_id: uuid.UUID, body: DecisionSupersede, principal: CurrentPrincipal
) -> Supersession:
    """Replaces an approved decision with a new one, keeping both.

    Only an `approved` decision may be superseded, and the old one is not edited — it
    gains a `superseded_by_id` and its status changes. That is what makes the record an
    audit trail rather than a current-state table.
    """
    # NOTE the order: the domain returns `(new_decision, old_decision)`, which reads
    # backwards next to the endpoint name. Named here rather than passed straight
    # through, because getting it wrong silently swaps two objects of the same type —
    # which is exactly what the test caught.
    new, old = domain.supersede_decision(
        str(decision_id),
        body.new_title,
        expected_version=body.expected_version,
        workspace_id=principal.workspace_id,
        agenda_item_id=str(body.agenda_item_id) if body.agenda_item_id else None,
        rationale=body.rationale,
    )
    return Supersession(superseded=old, replacement=new)
