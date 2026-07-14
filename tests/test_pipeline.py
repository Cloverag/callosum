"""Fast, deterministic tests — no LLM, no databases. Run in CI on every commit.

These cover the machinery the extraction quality depends on: chunk offsets, quote
location, and the verifier's quarantine logic. If these break, provenance is wrong
regardless of how good the model is.
"""

from callosum.extract import verify
from callosum.ingest import chunk, locate
from callosum.ontology import (
    Entity,
    EntityType,
    Extraction,
    FailureReason,
    Relationship,
    RelationType,
)


# --- chunk offsets ----------------------------------------------------------


def test_chunk_offsets_reproduce_source_exactly():
    text = "First paragraph here.\n\nSecond paragraph follows.\n\nThird and last one.\n\n" * 4
    chunks = chunk(text, target_tokens=30, overlap_tokens=8)
    assert chunks
    for c in chunks:
        # The invariant the entire provenance chain rests on.
        assert text[c.start_char : c.end_char] == c.text


def test_chunk_offsets_are_monotonic_within_a_chunk():
    text = "Alpha para.\n\nBeta para.\n\nGamma para.\n\n" * 5
    for c in chunk(text, target_tokens=25, overlap_tokens=5):
        assert 0 <= c.start_char < c.end_char <= len(text)


def test_empty_text_yields_no_chunks():
    assert chunk("") == []
    assert chunk("\n\n   \n\n") == []


# --- quote location ---------------------------------------------------------


def test_locate_exact():
    hay = "RAJ: We're not doing Model B. That's my call."
    span = locate("We're not doing Model B", hay)
    assert span is not None and hay[span[0] : span[1]] == "We're not doing Model B"


def test_locate_tolerates_reflowed_whitespace():
    hay = "PRIYA: I can't\n    recommend it at all."
    span = locate("I can't recommend it", hay)
    assert span is not None
    assert " ".join(hay[span[0] : span[1]].split()) == "I can't recommend it"


def test_locate_is_case_insensitive():
    assert locate("model b", "We rejected Model B outright.") is not None


def test_locate_rejects_paraphrase():
    # A paraphrase is a fabrication. It must not be located.
    assert locate("Priya disliked the pricing", "PRIYA: I can't recommend it.") is None


def test_locate_empty_quote():
    assert locate("", "anything") is None


# --- verifier / quarantine --------------------------------------------------


def _ext(rels):
    return Extraction(
        entities=[
            Entity(name="Raj", type=EntityType.PERSON),
            Entity(name="Reject Model B", type=EntityType.DECISION),
        ],
        relationships=rels,
    )


def test_verifier_keeps_grounded_edge_with_span():
    chunk_text = "RAJ: We're not doing Model B. Final answer."
    rel = Relationship(
        source="Raj", type=RelationType.APPROVED, target="Reject Model B",
        evidence="We're not doing Model B", confidence=0.95,
    )
    v = verify(_ext([rel]), chunk_text)
    assert len(v.relationships) == 1
    assert not v.failures
    start, end = v.spans[0]
    assert chunk_text[start:end] == "We're not doing Model B"


def test_verifier_quarantines_fabricated_quote():
    rel = Relationship(
        source="Raj", type=RelationType.OPPOSED, target="Reject Model B",
        evidence="Raj passionately defended Model B", confidence=0.9,
    )
    v = verify(_ext([rel]), "RAJ: We're not doing Model B.")
    assert not v.relationships
    assert len(v.failures) == 1
    assert v.failures[0].reason == FailureReason.QUOTE_NOT_FOUND
    # Quarantined, not dropped — the claim and its (false) confidence are preserved.
    assert v.failures[0].confidence == 0.9


def test_verifier_quarantines_edge_to_unextracted_entity():
    rel = Relationship(
        source="Raj", type=RelationType.APPROVED, target="Someone Not Extracted",
        evidence="We're not doing Model B", confidence=0.8,
    )
    v = verify(_ext([rel]), "RAJ: We're not doing Model B.")
    assert v.failures[0].reason == FailureReason.ENTITY_NOT_EXTRACTED


def test_verifier_quarantines_self_reference():
    rel = Relationship(
        source="Raj", type=RelationType.SUPPORTED, target="Raj",
        evidence="Raj", confidence=0.5,
    )
    v = verify(_ext([rel]), "Raj spoke.")
    assert v.failures[0].reason == FailureReason.SELF_REFERENCE


def test_verifier_quarantines_empty_quote():
    rel = Relationship(
        source="Raj", type=RelationType.APPROVED, target="Reject Model B",
        evidence="   ", confidence=0.7,
    )
    v = verify(_ext([rel]), "anything at all")
    assert v.failures[0].reason == FailureReason.QUOTE_EMPTY


def test_nothing_is_ever_silently_dropped():
    """Every proposed edge must end up either kept or quarantined — the count is
    conserved. A dropped edge is a lost measurement."""
    rels = [
        Relationship(source="Raj", type=RelationType.APPROVED, target="Reject Model B",
                     evidence="We're not doing Model B", confidence=0.9),   # kept
        Relationship(source="Raj", type=RelationType.OPPOSED, target="Reject Model B",
                     evidence="totally made up quote", confidence=0.9),      # quarantined
        Relationship(source="Raj", type=RelationType.SUPPORTED, target="Ghost",
                     evidence="We're not doing Model B", confidence=0.9),     # quarantined
    ]
    v = verify(_ext(rels), "RAJ: We're not doing Model B.")
    assert v.total_proposed == 3
    assert len(v.relationships) + len(v.failures) == 3
