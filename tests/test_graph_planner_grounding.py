import uuid
import pytest
from unittest.mock import MagicMock
from callosum.retrieve import Plan, Principal, plan, candidate_entities, Grounding


def test_plan_filtering_removes_unauthorized_entities():
    """Verify plan.entities filters out entity names not in known_entities."""
    known = ["Pricing Model B", "Board Meeting 12"]

    # Mock structured response with extra entity
    def mock_structured(system, question, schema, temperature=None):
        return Plan(
            entities=["Pricing Model B", "Secret Internal Project", "Board Meeting 12"],
            needs_graph=True,
            needs_vector=True,
            search_query="Pricing Model B rationale",
        )

    import callosum.retrieve as retrieve
    original_structured = retrieve.structured
    retrieve.structured = mock_structured

    try:
        p = plan("Why did we reject Pricing Model B?", known_entities=known)
        assert p.entities == ["Pricing Model B", "Board Meeting 12"]
        assert "Secret Internal Project" not in p.entities
    finally:
        retrieve.structured = original_structured


def test_plan_grounding_without_candidates():
    """Verify plan behavior when known_entities is None."""
    def mock_structured(system, question, schema, temperature=None):
        return Plan(
            entities=["Any Entity"],
            needs_graph=True,
            needs_vector=True,
            search_query="Query",
        )

    import callosum.retrieve as retrieve
    original_structured = retrieve.structured
    retrieve.structured = mock_structured

    try:
        p = plan("What is the status?", known_entities=None)
        assert p.entities == ["Any Entity"]
    finally:
        retrieve.structured = original_structured


def test_candidate_entities_empty_evidence():
    """Verify candidate_entities handles empty vector search results gracefully."""
    mock_conn = MagicMock()
    mock_driver = MagicMock()

    principal = Principal(
        id=uuid.uuid4(),
        name="Test Principal",
        role="founder",
        clearance=4,
        workspace_id=str(uuid.uuid4()),
    )

    import callosum.retrieve as retrieve
    original_vector_search = retrieve.vector_search
    original_entity_names = retrieve.store.entity_names_for_chunks

    retrieve.vector_search = MagicMock(return_value=([], 0))
    retrieve.store.entity_names_for_chunks = MagicMock(return_value=[])

    try:
        names, texts = candidate_entities(mock_conn, mock_driver, "Question?", principal)
        assert names == []
        assert texts == []
    finally:
        retrieve.vector_search = original_vector_search
        retrieve.store.entity_names_for_chunks = original_entity_names
