"""Resolution endpoints (Meridian P3, CP-B reads · CP-D writes — ADR-014).

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

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict

from meridian import resolutions as domain
from meridian.api.deps import CurrentPrincipal


class ResolutionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: uuid.UUID
    title: str
    body: str


class ResolutionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int
    title: str | None = None
    body: str | None = None


class VoteRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    board_member_id: uuid.UUID
    vote: str


class ResolutionTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_status: str
    expected_version: int


class ResolutionSupersede(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_title: str
    new_body: str
    expected_version: int


class ResolutionSupersession(BaseModel):
    """Both halves — the caller needs each."""

    superseded: domain.Resolution
    replacement: domain.Resolution

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


@router.post("", status_code=status.HTTP_201_CREATED)
def create_resolution(payload: ResolutionCreate, principal: CurrentPrincipal) -> domain.Resolution:
    """Drafts the formal instrument a decision produced."""
    return domain.create_resolution(
        str(payload.decision_id),
        payload.title,
        payload.body,
        workspace_id=principal.workspace_id,
    )


@router.patch("/{resolution_id}")
def update_resolution(
    resolution_id: uuid.UUID, payload: ResolutionPatch, principal: CurrentPrincipal
) -> domain.Resolution:
    """Edits a draft resolution under optimistic concurrency.

    `title` and `body` are both `NOT NULL`, so a `null` is refused at the boundary.
    """
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("expected_version", None)
    return domain.update_resolution(
        str(resolution_id),
        expected_version=payload.expected_version,
        workspace_id=principal.workspace_id,
        **changes,
    )


@router.post("/{resolution_id}/vote", status_code=status.HTTP_201_CREATED)
def record_vote(
    resolution_id: uuid.UUID, payload: VoteRecord, principal: CurrentPrincipal
) -> domain.ResolutionVote:
    """Records one director's vote.

    No `expected_version`, for the same reason as `record_stance`: this writes
    `resolution_vote`, not the resolution, so two directors voting at once do not
    contend.

    **The tally does not decide the outcome.** `resolutions.tally` is advisory and has
    no endpoint at all — it is a pure function, computed client-side from the votes this
    endpoint returns. Quorum and supermajority rules vary per board and nothing here
    records them, so inferring a result would assert governance nobody configured
    (#58 decision 2).
    """
    return domain.record_vote(
        str(resolution_id),
        str(payload.board_member_id),
        payload.vote,
        workspace_id=principal.workspace_id,
    )


@router.post("/{resolution_id}/transition")
def transition_resolution(
    resolution_id: uuid.UUID, payload: ResolutionTransition, principal: CurrentPrincipal
) -> domain.Resolution:
    """Moves a resolution through its lifecycle. A human sets the status, not the tally."""
    return domain.transition_resolution(
        str(resolution_id),
        payload.new_status,
        expected_version=payload.expected_version,
        workspace_id=principal.workspace_id,
    )


@router.post("/{resolution_id}/supersede", status_code=status.HTTP_201_CREATED)
def supersede_resolution(
    resolution_id: uuid.UUID, payload: ResolutionSupersede, principal: CurrentPrincipal
) -> ResolutionSupersession:
    """Replaces an adopted resolution with amended text, keeping both.

    **Votes are deliberately not copied forward.** They were cast on the old text, and
    carrying them over would record directors as having voted for words they never saw.
    """
    new, old = domain.supersede_resolution(
        str(resolution_id),
        payload.new_title,
        payload.new_body,
        expected_version=payload.expected_version,
        workspace_id=principal.workspace_id,
    )
    return ResolutionSupersession(superseded=old, replacement=new)


class BridgeCommitmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_board_member_id: uuid.UUID
    due_date: uuid.UUID | str | None = None


# ---------------------------------------------------------------------------
# There is deliberately NO `GET /{resolution_id}/policy-check` here.
#
# It existed, added in #119, and returned `quorum_met`, `threshold_passed` and
# `passed`. It is removed rather than fixed, because **#58 decision 2 says this
# product does not issue that verdict**:
#
#     The vote tally does not decide the outcome. `VoteTally.carried` is a simple
#     majority and explicitly advisory; a human sets `status`. Quorum and
#     supermajority rules vary per board and we have nowhere to record them, so
#     inferring the result would assert governance nobody configured.
#
# `record_vote` above and `transition_resolution` in the domain both restate it.
# The endpoint sat three functions below the docstring forbidding it.
#
# `domain.evaluate_resolution_policy` is KEPT, and its shape is now the one
# decision 2 sanctions: a pure function with no endpoint, exactly like
# `resolutions.tally`. A caller who has a board's standing orders in hand can
# evaluate against them; the API does not do it on their behalf and does not
# certify the result.
#
# The arithmetic was not sound either, which is why the denominator could not be
# fixed on its own. Measured against the live database on 2026-08-14:
#
#     roster : 1 voting, 1 non_voting, 1 standing-recused
#     votes  : voting→for, non_voting→recused, standing-recused→for
#     => quorum_percent_actual = 300.0%
#
# `total_participants` counts every recorded vote including `recused`, while
# `record_vote` permits a `non_voting` member to minute a recusal and does not
# restrain a standing-`recused` member at all. Any denominator narrower than the
# whole roster can therefore exceed 100%. Settling that needs `record_vote`'s
# guard, the numerator's definition and a stored policy decided together — see
# the decision issue.
# ---------------------------------------------------------------------------


@router.post("/{resolution_id}/bridge-commitment", status_code=status.HTTP_201_CREATED)
def bridge_resolution_to_commitment(
    resolution_id: uuid.UUID,
    payload: BridgeCommitmentRequest,
    principal: CurrentPrincipal,
) -> dict:
    """Converts an ADOPTED resolution into an actionable Commitment."""
    c = domain.bridge_resolution_to_commitment(
        str(resolution_id),
        owner_board_member_id=str(payload.owner_board_member_id),
        workspace_id=principal.workspace_id,
    )
    return {"status": "ok", "commitment_id": c.id}

