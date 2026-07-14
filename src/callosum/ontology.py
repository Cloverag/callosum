"""The graph ontology.

Every entity and relationship type here traces back to a requirement in the
Callosum PRD or the High-Value Use Cases doc (see reference/). Keep that
traceability: if a type can't be justified by a use case, it doesn't belong.

The two questions the ontology must answer, verbatim from the use-case doc:
  1. "Why did we reject this pricing model?"
     -> rationale, supporting documents, stakeholders, current execution status
  2. "Show every discussion about international expansion."
     -> decks, minutes, decisions, tasks
"""

from enum import StrEnum

from pydantic import BaseModel, Field

# Bump on any change to entity types, relation types, or their semantics. Stamped on
# every proposed change and every quarantined failure, so a result can always be
# attributed to the ontology that produced it — and so "re-extract everything under
# ontology v4" stays a meaningful instruction.
ONTOLOGY_VERSION = "1"


class FailureReason(StrEnum):
    """Why the evidence verifier refused an edge. These are the labels you will end
    up plotting: failure rate by reason, by model, by relation type, by chunk length."""

    QUOTE_NOT_FOUND = "quote_not_found"        # fabricated or paraphrased — the big one
    QUOTE_EMPTY = "quote_empty"                # model offered no evidence at all
    ENTITY_NOT_EXTRACTED = "entity_not_extracted"  # edge references an entity it never emitted
    SELF_REFERENCE = "self_reference"          # source == target


class EntityType(StrEnum):
    PERSON = "Person"              # founder, board member, investor, exec
    ORGANIZATION = "Organization"  # investor firm, customer, competitor
    MEETING = "Meeting"            # board meeting, standup, review
    DECISION = "Decision"          # the unit institutional memory exists to preserve
    DOCUMENT = "Document"          # deck, memo, contract, minutes
    TOPIC = "Topic"                # "Pricing Model B", "international expansion"
    ACTION_ITEM = "ActionItem"     # follow-up with an owner and a deadline
    METRIC = "Metric"              # ARR, burn, CAC — a KPI reported at a point in time


class RelationType(StrEnum):
    # Person -> Meeting / Decision
    ATTENDED = "ATTENDED"
    PROPOSED = "PROPOSED"
    SUPPORTED = "SUPPORTED"
    OPPOSED = "OPPOSED"
    APPROVED = "APPROVED"
    OWNS = "OWNS"                  # Person -> ActionItem | Topic
    WORKS_AT = "WORKS_AT"          # Person -> Organization

    # Decision -> everything else
    MADE_IN = "MADE_IN"            # Decision -> Meeting
    ABOUT = "ABOUT"                # Decision | Document -> Topic
    SUPERSEDES = "SUPERSEDES"      # Decision -> Decision (the version-history edge)

    # Provenance
    PRESENTED_AT = "PRESENTED_AT"  # Document -> Meeting
    EVIDENCE_FOR = "EVIDENCE_FOR"  # Document -> Decision
    REPORTED_IN = "REPORTED_IN"    # Metric -> Document | Meeting
    DERIVED_FROM = "DERIVED_FROM"  # ActionItem -> Decision


class DecisionStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    DEFERRED = "deferred"


class Entity(BaseModel):
    name: str = Field(description="Canonical name, exactly as written in the source text.")
    type: EntityType
    # Free-form because what matters differs per type: a Decision needs `status`
    # and `rationale`, a Metric needs `value` and `period`. Pinning a rigid schema
    # per type would multiply the tool surface for no retrieval benefit.
    attributes: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Type-specific fields. Decision: status (proposed|approved|rejected|"
            "superseded|deferred), rationale. Person: role, org. Meeting: date, kind. "
            "ActionItem: due, status. Metric: value, period. Omit what isn't stated."
        ),
    )


class Relationship(BaseModel):
    source: str = Field(description="Name of the source entity, matching an Entity.name exactly.")
    type: RelationType
    target: str = Field(description="Name of the target entity, matching an Entity.name exactly.")
    # The extractor must justify every edge with text it actually saw. This is the
    # anti-hallucination lever: an edge with no quote is an edge we reject.
    evidence: str = Field(
        description="Verbatim quote from the chunk that supports this relationship."
    )
    confidence: float = Field(ge=0.0, le=1.0)


class Extraction(BaseModel):
    """What one chunk yields. This is the tool schema the model fills in."""

    entities: list[Entity] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
