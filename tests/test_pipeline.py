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


def test_doctor_error_is_ascii_safe_on_legacy_windows_console(monkeypatch):
    """The health-error path must not crash while trying to print an error."""
    import pytest
    import typer
    import callosum.cli as cli

    messages = []

    class Console:
        def print(self, message):
            messages.append(message)

    monkeypatch.setattr(cli, "console", Console())
    monkeypatch.setattr(
        cli.llm,
        "health",
        lambda: (_ for _ in ()).throw(RuntimeError("Ollama unavailable: check \u2717")),
    )

    with pytest.raises(typer.Exit) as exited:
        cli.doctor()

    assert exited.value.exit_code == 1
    assert messages == [r"[red]ERROR[/] Ollama unavailable: check \u2717"]
    assert messages[0].isascii()


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


def test_every_gold_item_declares_existing_source_documents():
    """Gold expectations must point a reviewer to real corpus fixtures."""
    from pathlib import Path

    from callosum.evaluate import load_gold

    root = Path(__file__).resolve().parent.parent
    fixtures = {path.stem for path in (root / "data" / "demo").iterdir() if path.is_file()}
    gold = load_gold(root / "eval" / "gold.jsonl")
    assert gold
    for item in gold:
        assert item.source_documents, f"{item.id} has no source trace"
        assert set(item.source_documents) <= fixtures, item.id


def test_messy_email_gold_cases_are_seeded_with_document_provenance():
    from callosum.evaluate import GOLD_GROUPS, load_gold
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    groups = {title for title, _entities, _edges, _confidential in GOLD_GROUPS}
    items = {item.id: item for item in load_gold(root / "eval" / "gold.jsonl")}
    assert {"messy_board_followup_email", "messy_audit_followup_email"} <= groups
    assert items["D1"].source_documents == ["messy_board_followup_email"]
    assert items["D2"].source_documents == ["messy_audit_followup_email"]


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


def test_evaluation_report_renders_gold_source_documents():
    from callosum.evaluate import GoldItem, QuestionResult, StratumScore, render_markdown

    item = GoldItem(
        "D1", "messy_email", "Who owns it?", "Raj", [], [], [],
        source_documents=["messy_board_followup_email"],
    )
    normal = QuestionResult(item, True, True, 0.0, 0, False, [], 0.0, False, 1, 1)
    errored = QuestionResult(item, False, False, 0.0, 0, False, [], 0.0, False, 0, 0,
                             error="provider unavailable")
    scores = {"messy_email": StratumScore("messy_email", n=1, vector_correct=1,
                                           hybrid_correct=1)}
    report = render_markdown([normal, errored], scores, "test")
    assert "| id | stratum | sources |" in report
    assert report.count("messy_board_followup_email") == 2


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


# ---------------------------------------------------------------------------
# R12 — the candidate stage, measured as the ceiling it is
# ---------------------------------------------------------------------------


def test_ground_reports_the_candidates_it_offered_the_planner(monkeypatch):
    """The candidate list is evidence, not a debug aid — it must survive the call.

    Without it the eval cannot tell a linker error from a candidate miss, which is the
    whole reason grounding precision and recall could not be attributed in run 13.
    """
    import callosum.retrieve as retrieve

    monkeypatch.setattr(retrieve, "candidate_entities",
                        lambda *_a, **_k: (["Pricing Model B", "Board Meeting 12"], ["Context text"]))
    monkeypatch.setattr(
        retrieve, "structured",
        lambda *_a, **_k: Plan(entities=["Pricing Model B"], needs_graph=True,
                               needs_vector=True, search_query="pricing"),
    )

    g = retrieve.ground(None, None, "Why was pay-per-use rejected?", None)

    assert g.plan.entities == ["Pricing Model B"]
    assert g.candidates == ["Pricing Model B", "Board Meeting 12"]
    assert g.candidate_ms >= 0 and g.plan_ms >= 0


def test_grounded_plan_still_returns_a_plan(monkeypatch):
    """`ground` is the richer call; the old signature stays honest for existing callers."""
    import callosum.retrieve as retrieve

    monkeypatch.setattr(retrieve, "candidate_entities", lambda *_a, **_k: (["Pricing Model B"], ["Context text"]))
    monkeypatch.setattr(
        retrieve, "structured",
        lambda *_a, **_k: Plan(entities=["Pricing Model B"], needs_graph=True,
                               needs_vector=True, search_query="pricing"),
    )
    assert retrieve.grounded_plan(None, None, "q", None).entities == ["Pricing Model B"]


def test_candidate_recall_bounds_grounding_accuracy():
    """grounding_acc can never exceed candidate_recall — it is a ceiling, not a stat.

    If this inverts, the attribution table is lying: it would be claiming the linker
    grounded to something it was never offered.
    """
    from callosum.evaluate import GoldItem, QuestionResult, grounding_traversal

    facts = [{"subject": "Raj", "rel": "APPROVED", "target": "Reject Model B"}]
    item = GoldItem("A1", "grounding_adv", "q", "Raj", [], [], facts,
                    expect_entities=["Pricing Model B"])

    # Offered and linked correctly.
    hit = QuestionResult(item, True, True, 1.0, 2, True, ["Pricing Model B"], 0.0, False,
                         1, 1, candidates=["Pricing Model B"], candidate_hit=True)
    # Offered, linker picked a distractor — a linker failure.
    miss_link = QuestionResult(item, True, True, 0.0, 0, False, ["Board Meeting 12"], 0.0,
                               False, 1, 1,
                               candidates=["Pricing Model B", "Board Meeting 12"],
                               candidate_hit=True)
    # Never offered — no prompt change could have saved this one.
    miss_cand = QuestionResult(item, True, True, 0.0, 0, False, [], 0.0, False, 1, 1,
                               candidates=["Board Meeting 12"], candidate_hit=False)

    gt = grounding_traversal([hit, miss_link, miss_cand])

    import pytest

    # All three were retrieved (non-empty candidate lists), so all three are evaluated.
    assert gt["evaluated"] == 3
    assert gt["unretrieved"] == 0
    assert gt["grounding_acc"] <= gt["candidate_recall"]
    assert gt["candidate_recall"] == pytest.approx(2 / 3)   # offered on two of three
    assert gt["grounding_acc"] == pytest.approx(1 / 3)
    assert gt["linker_acc"] == pytest.approx(1 / 2)         # correct on one of two offered
    # The GER splits cleanly across the two stages, and the split accounts for all of it.
    assert gt["loss_to_candidates"] == pytest.approx(1 / 3)
    assert gt["loss_to_linker"] == pytest.approx(1 / 3)
    assert (gt["loss_to_candidates"] + gt["loss_to_linker"]
            + gt["grounding_acc"]) == pytest.approx(1.0)


def test_unretrieved_questions_are_excluded_from_grounding_not_scored_as_failures():
    """A question the candidate stage never retrieved must not count as a linker failure.

    This is the embedding-NaN case: the planner had no vocabulary, so scoring it as a
    grounding miss blames the linker for an infrastructure fault upstream (review
    2026-07-17). It is reported as `unretrieved`, and the rates are over what remained.
    """
    from callosum.evaluate import GoldItem, QuestionResult, grounding_traversal

    facts = [{"subject": "Raj", "rel": "APPROVED", "target": "Reject Model B"}]
    item = GoldItem("A1", "grounding_adv", "q", "Raj", [], [], facts,
                    expect_entities=["Pricing Model B"])

    grounded_ok = QuestionResult(item, True, True, 1.0, 2, True, ["Pricing Model B"], 0.0,
                                 False, 1, 1, candidates=["Pricing Model B"],
                                 candidate_hit=True)
    # Embedding died: no candidates reached the planner, nothing to ground against.
    embed_dead = QuestionResult(item, True, True, 0.0, 0, False, [], 0.0, False, 1, 1,
                                candidates=[], candidate_hit=False)

    gt = grounding_traversal([grounded_ok, embed_dead])

    assert gt["n"] == 2                    # two graph questions total
    assert gt["unretrieved"] == 1          # one never retrieved
    assert gt["evaluated"] == 1            # scored over the one that did
    assert gt["grounding_acc"] == 1.0      # NOT 50% — the dead one is excluded, not failed
    assert gt["candidate_recall"] == 1.0


def _fake_ollama_cfg():
    from types import SimpleNamespace
    from callosum.config import Provider
    return SimpleNamespace(provider=Provider.OLLAMA, ollama_host="http://x",
                           ollama_embedding_model="bge-m3")


class _Resp:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


def test_embed_recovers_deterministic_nan_via_one_normalized_retry(monkeypatch):
    """The input-specific bge-m3 NaN is rescued by a single normalized retry, not a loop."""
    import callosum.llm as llm
    from callosum.config import EMBEDDING_DIM

    monkeypatch.setattr(llm, "settings", _fake_ollama_cfg)
    good = [0.01] * EMBEDDING_DIM
    calls = []

    def fake_post(url, **kw):
        inp = kw["json"]["input"]
        calls.append(list(inp))
        # The exact failing string ends in '?'; the normalized retry drops it and succeeds.
        if inp[0].endswith("?"):
            return _Resp(500, text='{"error":"failed to encode response: unsupported value: NaN"}')
        return _Resp(200, {"embeddings": [good]})

    monkeypatch.setattr(llm.httpx, "post", fake_post)

    v = llm.embed(["a query that NaNs?"], input_type="query")

    assert len(v) == 1 and len(v[0]) == EMBEDDING_DIM
    assert calls == [["a query that NaNs?"], ["a query that NaNs"]]  # original, then normalized — exactly once


def test_embed_detects_nan_inside_a_200_response(monkeypatch):
    """A 200 whose vector contains NaN is treated as the fault, not returned to the caller."""
    import callosum.llm as llm
    from callosum.config import EMBEDDING_DIM

    monkeypatch.setattr(llm, "settings", _fake_ollama_cfg)
    good = [0.01] * EMBEDDING_DIM
    nan_vec = [float("nan")] + [0.0] * (EMBEDDING_DIM - 1)

    def fake_post(url, **kw):
        inp = kw["json"]["input"]
        return _Resp(200, {"embeddings": [nan_vec if inp[0].endswith("?") else good]})

    monkeypatch.setattr(llm.httpx, "post", fake_post)

    v = llm.embed(["poison?"], input_type="query")
    assert not any(x != x for x in v[0])  # no NaN survived to the caller


def test_embed_raises_and_excludes_when_normalized_retry_also_fails(monkeypatch):
    """If both attempts fail it raises (→ vector_search returns [] → question excluded)."""
    import callosum.llm as llm
    import pytest

    monkeypatch.setattr(llm, "settings", _fake_ollama_cfg)
    calls = []

    def always_nan(url, **kw):
        calls.append(list(kw["json"]["input"]))
        return _Resp(500, text="unsupported value: NaN")

    monkeypatch.setattr(llm.httpx, "post", always_nan)

    with pytest.raises(RuntimeError):
        llm.embed(["always bad?"], input_type="query")
    assert len(calls) == 2  # original + exactly one normalized retry, never a loop


def test_embed_does_not_retry_non_nan_errors(monkeypatch):
    """A 404/401 is not the recoverable case — surface it immediately, no normalized retry."""
    import callosum.llm as llm
    import pytest

    monkeypatch.setattr(llm, "settings", _fake_ollama_cfg)
    calls = []

    def not_found(url, **kw):
        calls.append(1)
        return _Resp(404, text="model not found")

    monkeypatch.setattr(llm.httpx, "post", not_found)

    with pytest.raises(Exception):
        llm.embed(["anything"], input_type="query")
    assert len(calls) == 1  # no normalized retry on a non-NaN error


def test_normalize_for_retry_is_minimal():
    from callosum.llm import _normalize_for_retry
    assert _normalize_for_retry("between the two board meetings?") == "between the two board meetings"
    assert _normalize_for_retry("no trailing punct") == "no trailing punct"
    assert _normalize_for_retry("trailing space ? ") == "trailing space"
    assert _normalize_for_retry("?") == "?"  # never returns empty


def test_ground_retry_recovers_a_transient_empty_candidate_list(monkeypatch):
    """The infra retry re-attempts an empty candidate list and takes the recovered one."""
    import callosum.evaluate as ev
    from callosum.retrieve import Grounding, Plan

    empty = Grounding(plan=Plan(entities=[], needs_graph=True, needs_vector=True,
                                search_query="q"),
                      candidates=[], candidate_ms=1, plan_ms=1)
    good = Grounding(plan=Plan(entities=["Pricing Model B"], needs_graph=True,
                               needs_vector=True, search_query="q"),
                     candidates=["Pricing Model B"], candidate_ms=1, plan_ms=1)
    calls = iter([empty, good])
    monkeypatch.setattr(ev, "ground", lambda *_a, **_k: next(calls))
    monkeypatch.setattr(ev.time, "sleep", lambda _s: None)  # don't actually wait in a test

    g = ev._ground_with_retry(None, None, "q", None, temperature=0.0)
    assert g.candidates == ["Pricing Model B"]


def test_ground_retry_is_bounded_and_gives_up_honestly(monkeypatch):
    """If every attempt fails, return the empty result so `unretrieved` can exclude it."""
    import callosum.evaluate as ev
    from callosum.retrieve import Grounding, Plan

    empty = Grounding(plan=Plan(entities=[], needs_graph=True, needs_vector=True,
                                search_query="q"),
                      candidates=[], candidate_ms=1, plan_ms=1)
    n = 0
    def counting(*_a, **_k):
        nonlocal n
        n += 1
        return empty
    monkeypatch.setattr(ev, "ground", counting)
    monkeypatch.setattr(ev.time, "sleep", lambda _s: None)

    g = ev._ground_with_retry(None, None, "q", None, temperature=0.0, retries=2)
    assert g.candidates == []          # gave up honestly, did not fabricate
    assert n == 3                      # initial attempt + 2 retries, no more


def test_coreference_negative_does_not_lower_linker_precision():
    """A coreference false-positive is a missing coref stage, not a linker abstention miss.

    Precision must be measured over abstention negatives (no referent at all); the
    coreference negative is reported on its own line (review 2026-07-17).
    """
    from callosum.evaluate import GoldItem, QuestionResult, grounding_traversal

    facts = [{"subject": "Raj", "rel": "APPROVED", "target": "Reject Model B"}]
    positive = GoldItem("A1", "grounding_adv", "q", "Raj", [], [], facts,
                        expect_entities=["Pricing Model B"])
    abst_neg = GoldItem("N1", "grounding_neg", "Why was the dynamic pricing engine rejected?",
                        "Raj", [], [], [], should_not_ground=True)
    coref_neg = GoldItem("K2", "coreference", "What does 'the prior motion' refer to?",
                         "Raj", [], [], [], should_not_ground=True)

    r_pos = QuestionResult(positive, True, True, 1.0, 2, True, ["Pricing Model B"], 0.0,
                           False, 1, 1, candidates=["Pricing Model B"], candidate_hit=True)
    # Abstention negative: linker correctly abstained (no false positive).
    r_abst = QuestionResult(abst_neg, True, True, 0.0, 0, False, [], 0.0, False, 1, 1,
                            candidates=["Pricing Model B"], candidate_hit=False)
    # Coreference negative: linker grounded to a real node — but that's a coref gap.
    r_coref = QuestionResult(coref_neg, True, True, 0.0, 0, False, ["Board Meeting 16"],
                             0.0, True, 1, 1, candidates=["Board Meeting 16"],
                             candidate_hit=False)

    gt = grounding_traversal([r_pos, r_abst, r_coref])

    assert gt["n_neg"] == 1                     # only the abstention negative
    assert gt["false_positives"] == 0
    assert gt["grounding_precision"] == 1.0     # NOT dragged down by the coref miss
    assert gt["n_neg_coref"] == 1               # coref negative counted separately
    assert gt["coref_false_positives"] == 1


def test_csv_schema_change_never_corrupts_the_existing_log(tmp_path):
    """An old log under a narrower header must be left alone, byte for byte.

    eval/results.csv is the eval chapter's raw data across every run. Appending wider
    rows under the old header would shift each field silently and damage the HISTORY,
    not the new run — so a schema mismatch rotates to a sibling instead.
    """
    from callosum.evaluate import CSV_COLUMNS, GoldItem, QuestionResult, write_csv

    log = tmp_path / "results.csv"
    old = "run,model,id,stratum,question,error\n2026-07-16 10:00,gpt-oss,A1,lookup,q,\n"
    log.write_text(old, encoding="utf-8")

    item = GoldItem("A1", "lookup", "q", "Raj", [], [], [])
    r = QuestionResult(item, True, True, 0.0, 0, False, [], 0.0, False, 1, 1)

    written = write_csv([r], log, "gpt-oss")

    assert written == tmp_path / "results-v2.csv"
    assert log.read_text(encoding="utf-8") == old, "the old log was modified"
    rows = written.read_text(encoding="utf-8").splitlines()
    assert rows[0] == ",".join(CSV_COLUMNS)
    assert len(rows) == 2


def test_csv_appends_in_place_when_the_schema_already_matches(tmp_path):
    """Rotation is for schema drift only — matching runs must keep sharing one file."""
    from callosum.evaluate import GoldItem, QuestionResult, write_csv

    log = tmp_path / "results.csv"
    item = GoldItem("A1", "lookup", "q", "Raj", [], [], [])
    r = QuestionResult(item, True, True, 0.0, 0, False, [], 0.0, False, 1, 1)

    assert write_csv([r], log, "gpt-oss") == log
    assert write_csv([r], log, "gpt-oss") == log       # second run appends, no rotation
    assert not (tmp_path / "results-v2.csv").exists()
    assert len(log.read_text(encoding="utf-8").splitlines()) == 3   # header + two rows


def test_candidate_list_is_logged_verbatim_for_the_audit(tmp_path):
    """When the linker false-positives, the row must show which distractors it saw."""
    from callosum.evaluate import GoldItem, QuestionResult, write_csv

    item = GoldItem("N1", "grounding_neg", "Why was the dynamic pricing engine rejected?",
                    "Raj", [], [], [], should_not_ground=True)
    r = QuestionResult(item, True, True, 0.0, 0, False, ["Pricing Model B"], 0.0, True,
                       1, 1, candidates=["Pricing Model B", "Board Meeting 12"],
                       candidate_hit=False, candidate_ms=42, plan_ms=310)

    written = write_csv([r], tmp_path / "results.csv", "gpt-oss")
    row = written.read_text(encoding="utf-8").splitlines()[1]

    assert "Pricing Model B|Board Meeting 12" in row
    assert "42" in row and "310" in row
