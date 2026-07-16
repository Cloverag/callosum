"""Fast, deterministic tests — no LLM, no databases. Run in CI on every commit.

These cover the machinery the extraction quality depends on: chunk offsets, quote
location, and the verifier's quarantine logic. If these break, provenance is wrong
regardless of how good the model is.
"""

from callosum.extract import verify
from callosum.ingest import chunk, locate
from callosum.retrieve import Plan, _render_chain
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


def test_locate_rejects_stitched_quote():
    """The failure that actually occurred on the first real ingest: the model stitched
    two non-adjacent sentences into one quote, in one case across two speakers —
    attributing one person's words to another. A stitched quote is not a contiguous
    span and must not locate. (docs/findings.md, 2026-07-15)"""
    hay = (
        "RAJ: We're not doing Model B. We'll stay on per-seat.\n"
        "TOM: For the minutes?\n"
        "RAJ: Rejection for this fiscal year."
    )
    # Stitched across a gap -> rejected.
    assert locate("We're not doing Model B. Rejection for this fiscal year.", hay) is None
    # The correct contiguous span still locates.
    assert locate("We're not doing Model B.", hay) is not None


def test_locate_tolerates_typographic_glyphs():
    """Curly quotes and em-dashes are encoding variants, not fabrications. The model
    emits them where the source has ASCII; treating that as a mismatch would inflate
    the fabrication rate (it turned 1 real quarantine into 17 before this fix)."""
    hay = "RAJ: We're not doing it — that's my call."
    assert locate("We’re not doing it — that’s my call.", hay) is not None


def test_locate_empty_quote():
    assert locate("", "anything") is None


# --- multi-hop chain rendering ----------------------------------------------


def test_render_chain_respects_edge_direction():
    """The money-shot the graph produces and vectors can't: a person connected to a
    decision through a meeting. Arrow direction must reflect each edge's real
    orientation, not the order we happened to walk the path."""
    names = ["Marcus", "Board Meeting 12", "Reject Model B"]
    rels = ["ATTENDED", "MADE_IN"]
    # Marcus -ATTENDED-> Meeting  (start == first node, forward)
    # Decision -MADE_IN-> Meeting (start == last node, so against our walk => backward)
    starts = ["Marcus", "Reject Model B"]
    chain = _render_chain(names, rels, starts)
    assert chain == "path: Marcus —ATTENDED→ Board Meeting 12 ←MADE_IN— Reject Model B"


def test_render_chain_all_forward():
    names = ["Raj", "Reject Model B", "Pricing Model B"]
    rels = ["APPROVED", "ABOUT"]
    starts = ["Raj", "Reject Model B"]
    chain = _render_chain(names, rels, starts)
    assert chain == "path: Raj —APPROVED→ Reject Model B —ABOUT→ Pricing Model B"


def test_plan_discards_names_outside_permission_scoped_candidates(monkeypatch):
    """A model cannot smuggle a graph name past the candidate/RBAC boundary."""
    import callosum.retrieve as retrieve

    monkeypatch.setattr(
        retrieve,
        "structured",
        lambda *_args, **_kwargs: Plan(
            entities=["Pricing Model B", "Restricted Compensation Plan"],
            needs_graph=True,
            needs_vector=True,
            search_query="pricing",
        ),
    )
    result = retrieve.plan("Why was pricing rejected?", ["Pricing Model B"])
    assert result.entities == ["Pricing Model B"]


def test_plan_keeps_an_explicit_abstention(monkeypatch):
    import callosum.retrieve as retrieve

    monkeypatch.setattr(
        retrieve,
        "structured",
        lambda *_args, **_kwargs: Plan(
            entities=[], needs_graph=True, needs_vector=True, search_query="unrelated topic"
        ),
    )
    result = retrieve.plan("Why was the dynamic pricing engine rejected?", ["Pricing Model B"])
    assert result.entities == []


def test_candidate_entity_query_repeats_clearance_gate():
    """Candidate names are permission-filtered before they reach the planner prompt."""
    import uuid
    from callosum.store import entity_names_for_chunks

    class Session:
        def __init__(self):
            self.query = ""
            self.params = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def run(self, query, **params):
            self.query, self.params = query, params
            return [{"name": "Pricing Model B"}]

    class Driver:
        def __init__(self):
            self.session_obj = Session()

        def session(self):
            return self.session_obj

    driver = Driver()
    assert entity_names_for_chunks(driver, [uuid.uuid4()], 1) == ["Pricing Model B"]
    assert "c.sensitivity <= $clearance" in driver.session_obj.query
    assert driver.session_obj.params["clearance"] == 1


# --- gold graph / gold questions consistency --------------------------------


def test_gold_edges_reference_defined_entities():
    """Every seeded edge must connect entities the seed also creates (across ALL
    document groups — cross-document edges like SUPERSEDES reference an entity defined in
    a different group). A dangling endpoint would MATCH nothing and be silently dropped."""
    from callosum.evaluate import GOLD_GROUPS

    names = {n for _t, ents, _e, _c in GOLD_GROUPS for n, _et, _a in ents}
    for _title, _ents, edges, _conf in GOLD_GROUPS:
        for src, _rel, tgt, _q in edges:
            assert src in names, f"edge source {src!r} is not a defined gold entity"
            assert tgt in names, f"edge target {tgt!r} is not a defined gold entity"


def test_every_expected_fact_is_a_seeded_edge():
    """The eval's expected graph facts must be reachable in the seeded graph. If a gold
    question expects an edge the seed never writes, the eval can never pass it — that is
    a gold-set bug, not a system failure, and this test catches it before a run."""
    from pathlib import Path

    from callosum.evaluate import GOLD_GROUPS, load_gold

    seeded = [
        (src.lower(), rel.value.lower(), tgt.lower())
        for _t, _ents, edges, _c in GOLD_GROUPS
        for src, rel, tgt, _q in edges
    ]
    gold = load_gold(Path(__file__).resolve().parent.parent / "eval" / "gold.jsonl")
    for item in gold:
        for want in item.expect_facts:
            s, r, t = want["subject"].lower(), want["rel"].lower(), want["target"].lower()
            ok = any(s in es and r == er and t in et for es, er, et in seeded)
            assert ok, f"{item.id}: expected fact {want} matches no seeded gold edge"


def test_aliases_and_conflicting_forecasts_keep_distinct_provenance():
    """R8/R9 must add evidence-backed links, never destructive name or value merges."""
    from callosum.evaluate import GOLD_GROUPS

    edges_by_title = {title: edges for title, _ents, edges, _conf in GOLD_GROUPS}
    aliases = edges_by_title["board_meeting_14_transcript"]
    assert ("Raj", RelationType.ALIAS_OF, "Rajesh Malhotra",
            "Raj, short for Rajesh Malhotra") in aliases
    assert not any(src == "Raj Patel" and rel == RelationType.ALIAS_OF for src, rel, _tgt, _q in aliases)

    finance = edges_by_title["finance_fy27_forecast"]
    sales = edges_by_title["sales_fy27_forecast"]
    assert finance[0][0] == "Finance FY27 ARR forecast"
    assert sales[0][0] == "Sales FY27 ARR forecast"
    assert finance[0][0] != sales[0][0]


def test_messy_document_fixtures_load_for_every_supported_format():
    """R11 keeps a real fixture for each loader rather than testing only clean TXT."""
    from pathlib import Path

    from callosum.ingest import load

    root = Path(__file__).resolve().parent.parent / "data" / "demo"
    fixtures = {
        "messy_operations_notes.txt": "northwind min spend",
        "messy_customer_email.md": "$11.6M",
        "messy_customer_call.vtt": "not final",
        "messy_operational_risk_memo.docx": "OCR-cleaned scan",
        "messy_board_appendix.pdf": "No board-approved FY27 target",
    }
    for name, expected in fixtures.items():
        assert expected.lower() in load(root / name).lower(), name


def test_messy_restricted_fixture_is_explicitly_confidential():
    """The R11 corpus keeps restricted content visible to the RBAC test setup."""
    from pathlib import Path

    text = (Path(__file__).resolve().parent.parent / "data" / "demo" /
            "messy_restricted_email.md").read_text(encoding="utf-8")
    assert "CONFIDENTIAL" in text and "$210K" in text


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


# --- eval scorer ------------------------------------------------------------


def _answer(text, facts=None):
    from callosum.retrieve import Answer
    return Answer(text=text, evidence=[], graph_facts=facts or [], withheld=0, latency_ms=0)


def test_answer_correct_requires_all_expected_strings():
    from callosum.evaluate import GoldItem, _answer_correct
    item = GoldItem("M1", "multi_hop", "q", "Raj", ["Marcus", "Priya"], [], [])
    assert _answer_correct(_answer("Marcus opposed, Priya supported"), item)
    assert not _answer_correct(_answer("Only Marcus is mentioned"), item)


def test_answer_correct_forbidden_string_is_automatic_fail():
    """The RBAC negative test: the secret must never appear, whatever else is said."""
    from callosum.evaluate import GoldItem, _answer_correct
    item = GoldItem("X1", "rbac", "q", "Marcus", [], ["185"], [])
    assert _answer_correct(_answer("I cannot share that."), item)
    assert not _answer_correct(_answer("Her base is $185K."), item)
    # A forbidden hit fails even when an expected string is also present.
    item2 = GoldItem("X", "rbac", "q", "M", ["Priya"], ["185"], [])
    assert not _answer_correct(_answer("Priya earns $185K."), item2)


def test_graph_fact_recall_matches_on_tokens_not_glyphs():
    from callosum.evaluate import GoldItem, _graph_fact_recall
    item = GoldItem(
        "R1", "relational", "q", "Raj", ["Marcus"], [],
        [{"subject": "Marcus", "rel": "OPPOSED", "target": "Reject Pricing Model B"}],
    )
    # Rendered with em-dash arrows — must still match on tokens.
    hit = _answer("", ["Marcus Webb —OPPOSED→ Reject Pricing Model B  (evidence: \"...\")"])
    assert _graph_fact_recall(hit, item) == 1.0
    miss = _answer("", ["Priya Nair —SUPPORTED→ Reject Pricing Model B"])
    assert _graph_fact_recall(miss, item) == 0.0


def test_graph_fact_recall_is_fractional():
    from callosum.evaluate import GoldItem, _graph_fact_recall
    item = GoldItem(
        "M1", "multi_hop", "q", "Raj", [], [],
        [{"subject": "Marcus", "rel": "OPPOSED", "target": "Reject Pricing Model B"},
         {"subject": "Priya", "rel": "SUPPORTED", "target": "Reject Pricing Model B"}],
    )
    one_of_two = _answer("", ["Marcus Webb —OPPOSED→ Reject Pricing Model B"])
    assert _graph_fact_recall(one_of_two, item) == 0.5


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
