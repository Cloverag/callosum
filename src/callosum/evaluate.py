"""Phase 7 evaluation — stratified, hybrid vs vector-only.

The thesis claim is not "hybrid retrieval is better on average." Averages mush the one
result that matters. The claim is specific and directional:

    - on **lookup** questions ("what is the runway?") the answer is sitting in a chunk,
      so vector search alone finds it and the graph adds nothing — the two conditions
      should TIE.
    - on **relational** and especially **multi-hop** questions ("which board members
      took a position on usage-based pricing?") the answer is a *join* the graph makes
      and a single chunk does not contain, so vector-only should LOSE.
    - on **rbac** questions the point is not retrieval quality but that a low-clearance
      caller is refused regardless of condition.

So we evaluate per stratum, not in aggregate, and we measure two things per question:

    1. answer correctness — cheap, deterministic string check (does the required fact
       appear; does a forbidden secret NOT appear). No LLM judge: the gold strings are
       chosen to be unambiguous, and a deterministic check is reproducible in a way an
       LLM grader is not.
    2. graph-fact recall (hybrid only) — was the specific relational edge the question
       needs actually present in the graph context? This is the mechanism-level number:
       it isolates the graph's contribution from the synthesiser's prose, and it is
       zero for vector-only *by construction* (there is no graph context to contain it).

The instrument is honest about its own limits: on a small single-transcript corpus,
vector-only can often reconstruct a relationship because the whole conversation is in
one retrievable passage. Where that happens the strata will not separate, and that is a
finding about the corpus, not a bug in the graph. Expanding the corpus so multi-hop
joins genuinely cross chunks is the next lever — see docs/findings.md.
"""

import csv
import itertools
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
from neo4j import Driver

from callosum import store
from callosum.ontology import EntityType, RelationType
from callosum.retrieve import Answer, Principal, ask, graph_search, ground, plan

STRATUM_ORDER = ["lookup", "relational", "multi_hop", "temporal",
                 "aliases", "conflict", "coreference", "messy_email", "grounding_adv", "grounding_neg", "rbac"]


# ---------------------------------------------------------------------------
# Gold graph — the fixed knowledge base the retrieval eval measures against
# ---------------------------------------------------------------------------
#
# These edges are NOT extracted. They are the ground truth any reader confirms by
# reading data/demo/board_meeting_12_transcript.txt — Raj approved the rejection,
# Marcus opposed it, and so on. Seeding them deterministically is what lets the eval
# measure *retrieval* rather than which edges extraction happened to keep this run
# (docs/findings.md, run 6). Extraction quality is a separate experiment with its own
# scorecard (the quarantine stats); conflating the two is the confusion run 6 exposed.
#
# The quotes are real spans from the transcript. They are stamped onto the edges for
# display and citation exactly as an approved edge would be; the seed simply skips the
# stochastic LLM step in between. Say so in the thesis: the eval graph is a gold
# standard, declared as such.

# The gold graph is grouped by SOURCE DOCUMENT. Each edge is attached to a chunk of the
# document it actually came from (document-aware seeding), so as the corpus grows the
# evaluator never leans on "sensitivity == board" to place an edge — document identity is
# the correct key. Meeting 12 is polarity; Meeting 13 is temporal / decision evolution.

# --- Board Meeting 12 (sensitivity 1) — the pricing REJECTION -----------------
GOLD_M12_ENTITIES = [
    ("Raj Malhotra", EntityType.PERSON, {"role": "CEO, co-founder"}),
    ("Priya Nair", EntityType.PERSON, {"role": "CFO"}),
    ("Marcus Webb", EntityType.PERSON, {"role": "Sequoia, board"}),
    ("Reject Pricing Model B", EntityType.DECISION, {"status": "rejected"}),
    ("Pricing Model B", EntityType.TOPIC, {}),
    ("Board Meeting 12", EntityType.MEETING, {}),
    ("Write pricing decision pack", EntityType.ACTION_ITEM, {"owner": "Priya Nair"}),
]
GOLD_M12_EDGES = [
    ("Reject Pricing Model B", RelationType.ABOUT, "Pricing Model B",
     "Pricing Model B — the usage-based tier"),
    ("Reject Pricing Model B", RelationType.MADE_IN, "Board Meeting 12",
     "Board Meeting 12"),
    ("Raj Malhotra", RelationType.APPROVED, "Reject Pricing Model B",
     "We're not doing Model B."),
    ("Priya Nair", RelationType.SUPPORTED, "Reject Pricing Model B",
     "I can't recommend it in its current form."),
    ("Marcus Webb", RelationType.OPPOSED, "Reject Pricing Model B",
     "I want to push back on that framing."),
    ("Write pricing decision pack", RelationType.DERIVED_FROM, "Reject Pricing Model B",
     "write it up for the board pack with the margin analysis attached"),
]

# --- Board Meeting 13 (sensitivity 1) — the REVERSAL, seven months later ------
# The decision that SUPERSEDES the March rejection, plus the customer that drove it
# (REQUESTED, ontology v2), the metric/document reference, and Tom's workstream. This is
# the temporal-reasoning stress case: the answer to "is Model B rejected?" now depends on
# an edge in a *different* document.
GOLD_M13_ENTITIES = [
    ("Elena Duarte", EntityType.PERSON, {"role": "Accel, board"}),
    ("Tom Fischer", EntityType.PERSON, {"role": "independent director"}),
    ("Adopt Usage-Based Pricing", EntityType.DECISION, {"status": "approved"}),
    ("Board Meeting 13", EntityType.MEETING, {}),
    ("Northwind", EntityType.ORGANIZATION, {"role": "largest customer"}),
    ("March Board Deck", EntityType.DOCUMENT, {}),
    ("gross margin", EntityType.METRIC, {"value": "66%", "period": "next year"}),
    ("Germany Expansion", EntityType.TOPIC, {}),
]
GOLD_M13_EDGES = [
    ("Adopt Usage-Based Pricing", RelationType.SUPERSEDES, "Reject Pricing Model B",
     "I'm comfortable reversing our decision from March"),
    ("Adopt Usage-Based Pricing", RelationType.ABOUT, "Pricing Model B",
     "usage-based is our forward pricing model"),
    ("Adopt Usage-Based Pricing", RelationType.MADE_IN, "Board Meeting 13",
     "Board Meeting 13"),
    ("Raj Malhotra", RelationType.APPROVED, "Adopt Usage-Based Pricing",
     "usage-based is our forward pricing model. That's my call."),
    ("Marcus Webb", RelationType.SUPPORTED, "Adopt Usage-Based Pricing",
     "I supported this a year ago and I support it now"),
    ("Priya Nair", RelationType.SUPPORTED, "Adopt Usage-Based Pricing",
     "With that floor and the Series C closed, I can get behind it. I'm a yes."),
    ("Elena Duarte", RelationType.SUPPORTED, "Adopt Usage-Based Pricing",
     "so I'm supportive of the direction"),
    ("Northwind", RelationType.REQUESTED, "Pricing Model B",
     "Our single largest account has formally asked to move to a usage-based contract"),
    ("gross margin", RelationType.REPORTED_IN, "March Board Deck",
     "Appendix C in the March board deck projected gross margin at 71%"),
    ("Tom Fischer", RelationType.OWNS, "Germany Expansion",
     "Tom owns the Germany expansion workstream through Q2"),
]

# --- Compensation review (sensitivity 3) — founder/exec only ------------------
# This edge exists solely to exercise the graph-side RBAC gate: its quote embeds a salary,
# so if the path gate ever failed open, an investor asking about Priya would receive
# "$185K" through it — the leak fixed in run 3. It makes the X1 rbac case a real test of
# the graph gate, not only the vector filter.
GOLD_CONFIDENTIAL_ENTITIES = [
    ("Meridian Inc", EntityType.ORGANIZATION, {}),
]
GOLD_CONFIDENTIAL_EDGES = [
    ("Priya Nair", RelationType.WORKS_AT, "Meridian Inc",
     "Priya Nair, CFO, is at $185K base"),
]

# --- Board Meeting 14 (sensitivity 1) — reviewed aliases, not auto-merges ---------
GOLD_M14_ENTITIES = [
    ("Rajesh Malhotra", EntityType.PERSON, {"role": "CEO, co-founder"}),
    ("Raj", EntityType.PERSON, {"source_spelling": "Raj"}),
    ("R. Malhotra", EntityType.PERSON, {"source_spelling": "R. Malhotra"}),
    ("Raj Patel", EntityType.PERSON, {"role": "guest observer"}),
    ("Board Meeting 14", EntityType.MEETING, {}),
]
GOLD_M14_EDGES = [
    ("Raj", RelationType.ALIAS_OF, "Rajesh Malhotra", "Raj, short for Rajesh Malhotra"),
    ("R. Malhotra", RelationType.ALIAS_OF, "Rajesh Malhotra", "R. Malhotra, the same CEO"),
    ("Rajesh Malhotra", RelationType.ATTENDED, "Board Meeting 14", "Rajesh Malhotra (CEO, co-founder)"),
    ("Raj Patel", RelationType.ATTENDED, "Board Meeting 14", "Raj Patel (guest observer, not Rajesh Malhotra)"),
]

# --- Meeting 15 conflict sources (sensitivity 1) ---------------------------------
GOLD_FINANCE_ENTITIES = [("Finance FY27 ARR forecast", EntityType.METRIC, {"value": "$12.0M", "period": "FY27"})]
GOLD_FINANCE_EDGES = [("Finance FY27 ARR forecast", RelationType.REPORTED_IN, "Finance FY27 Forecast", "Finance forecast: FY27 ARR is $12.0M.")]
GOLD_SALES_ENTITIES = [("Sales FY27 ARR forecast", EntityType.METRIC, {"value": "$11.6M", "period": "FY27"})]
GOLD_SALES_EDGES = [("Sales FY27 ARR forecast", RelationType.REPORTED_IN, "Sales FY27 Forecast", "Sales forecast: FY27 ARR is $11.6M.")]
GOLD_M15_ENTITIES = [
    ("Board Meeting 15", EntityType.MEETING, {}),
    ("Finance FY27 Forecast", EntityType.DOCUMENT, {}),
    ("Sales FY27 Forecast", EntityType.DOCUMENT, {}),
    ("FY27 ARR forecast", EntityType.TOPIC, {}),
]
GOLD_M15_EDGES = [
    ("Finance FY27 Forecast", RelationType.PRESENTED_AT, "Board Meeting 15", "The Finance FY27 Forecast says $12.0M; the Sales FY27 Forecast says $11.6M."),
    ("Sales FY27 Forecast", RelationType.PRESENTED_AT, "Board Meeting 15", "The Finance FY27 Forecast says $12.0M; the Sales FY27 Forecast says $11.6M."),
    ("Finance FY27 Forecast", RelationType.ABOUT, "FY27 ARR forecast", "The Finance FY27 Forecast says $12.0M"),
    ("Sales FY27 Forecast", RelationType.ABOUT, "FY27 ARR forecast", "the Sales FY27 Forecast says $11.6M"),
]

# --- Board Meeting 16 (sensitivity 1) — context-dependent references -----------
GOLD_M16_ENTITIES = [
    ("Board Meeting 16", EntityType.MEETING, {}),
    ("Pricing rollout plan", EntityType.ACTION_ITEM, {"owner": "Priya Nair"}),
    ("International expansion motion", EntityType.DECISION, {"status": "deferred"}),
]
GOLD_M16_EDGES = [
    ("Pricing rollout plan", RelationType.DERIVED_FROM, "Adopt Usage-Based Pricing", "That proposal means the pricing rollout plan Priya circulated yesterday."),
    ("Priya Nair", RelationType.OWNS, "Pricing rollout plan", "Priya owns that pricing rollout plan."),
    ("International expansion motion", RelationType.MADE_IN, "Board Meeting 16", "The international expansion motion stays deferred."),
]

# --- Messy follow-up emails (sensitivity 1) - operational records, not resolutions ---
GOLD_MESSY_BOARD_EMAIL_ENTITIES = [
    ("Vendor security questionnaire", EntityType.ACTION_ITEM, {"owner": "Priya Nair"}),
]
GOLD_MESSY_BOARD_EMAIL_EDGES = [
    ("Priya Nair", RelationType.OWNS, "Vendor security questionnaire",
     "Priya owns the vendor-security questionnaire"),
]
GOLD_MESSY_AUDIT_EMAIL_ENTITIES = [
    ("Nisha Shah", EntityType.PERSON, {"role": "security operations"}),
    ("SOC 2 evidence request", EntityType.ACTION_ITEM, {"owner": "Nisha Shah"}),
]
GOLD_MESSY_AUDIT_EMAIL_EDGES = [
    ("Nisha Shah", RelationType.OWNS, "SOC 2 evidence request",
     "Nisha owns the SOC 2 evidence request"),
]

# (document title -> entities, edges). Title is the file stem, as ingest.upsert_document
# stores it. Confidential group last; its edge count is reported separately.
GOLD_GROUPS = [
    ("board_meeting_12_transcript", GOLD_M12_ENTITIES, GOLD_M12_EDGES, False),
    ("board_meeting_13_transcript", GOLD_M13_ENTITIES, GOLD_M13_EDGES, False),
    ("board_meeting_14_transcript", GOLD_M14_ENTITIES, GOLD_M14_EDGES, False),
    ("finance_fy27_forecast", GOLD_FINANCE_ENTITIES + [("Finance FY27 Forecast", EntityType.DOCUMENT, {})], GOLD_FINANCE_EDGES, False),
    ("sales_fy27_forecast", GOLD_SALES_ENTITIES + [("Sales FY27 Forecast", EntityType.DOCUMENT, {})], GOLD_SALES_EDGES, False),
    ("board_meeting_15_transcript", GOLD_M15_ENTITIES, GOLD_M15_EDGES, False),
    ("board_meeting_16_transcript", GOLD_M16_ENTITIES, GOLD_M16_EDGES, False),
    ("messy_board_followup_email", GOLD_MESSY_BOARD_EMAIL_ENTITIES, GOLD_MESSY_BOARD_EMAIL_EDGES, False),
    ("messy_audit_followup_email", GOLD_MESSY_AUDIT_EMAIL_ENTITIES, GOLD_MESSY_AUDIT_EMAIL_EDGES, False),
    ("compensation_review_CONFIDENTIAL", GOLD_CONFIDENTIAL_ENTITIES, GOLD_CONFIDENTIAL_EDGES, True),
]


def seed_graph(conn: psycopg.Connection, driver: Driver) -> tuple[int, int]:
    """Write the gold graph directly, bypassing the LLM. Returns (edges, confidential).

    Document-aware: each group's edges are attached to a chunk of the document they came
    from (matched by title), so an edge's provenance chunk is correct even when several
    documents share a sensitivity level. Requires the documents to already be ingested
    (chunks + embeddings in Postgres, Chunk nodes in Neo4j). A group whose document is not
    present is skipped — the seed only replaces the *approval* step, not ingestion.
    ALL entities are seeded before ANY edges, so cross-document edges (e.g. Meeting 13's
    decision SUPERSEDES Meeting 12's) find both endpoints. MERGE-based, so re-seeding is
    a no-op.
    """
    def chunk_for(title: str) -> str | None:
        row = conn.execute(
            "SELECT c.id FROM chunk c JOIN document d ON d.id = c.document_id "
            "WHERE d.title = %s ORDER BY c.ordinal LIMIT 1",
            (title,),
        ).fetchone()
        return str(row["id"]) if row else None

    chunks = {title: chunk_for(title) for title, _, _, _ in GOLD_GROUPS}
    if not chunks.get("board_meeting_12_transcript"):
        raise ValueError(
            "board_meeting_12_transcript not ingested. Run scripts/eval.sh, which ingests "
            "the documents before seeding."
        )

    def put_entity(name: str, etype: EntityType, attrs: dict, chunk_id: str) -> None:
        store.apply_entity(driver, {
            "name": name, "type": etype.value, "attributes": attrs, "chunk_id": chunk_id,
        })

    def put_edge(src: str, rel: RelationType, tgt: str, quote: str, chunk_id: str) -> None:
        store.apply_relationship(driver, {
            "source": src, "type": rel.value, "target": tgt,
            "quote": quote, "chunk_id": chunk_id,
        })

    # Pass 1: all entities (a cross-document edge needs both endpoints to already exist).
    for title, entities, _edges, _conf in GOLD_GROUPS:
        cid = chunks.get(title)
        if not cid:
            continue
        for name, etype, attrs in entities:
            put_entity(name, etype, attrs, cid)

    # Pass 2: all edges, each stamped with its own document's chunk.
    total = confidential = 0
    for title, _entities, edges, is_conf in GOLD_GROUPS:
        cid = chunks.get(title)
        if not cid:
            continue
        for src, rel, tgt, quote in edges:
            put_edge(src, rel, tgt, quote, cid)
            total += 1
            if is_conf:
                confidential += 1

    return total, confidential


@dataclass
class GoldItem:
    id: str
    stratum: str
    question: str
    as_user: str
    expect_answer: list[str]
    forbid_answer: list[str]
    expect_facts: list[dict]
    # Canonical node name(s) the planner should ground this question's mention to. Any
    # one counts (a pricing question may legitimately seed the Topic OR the Decision).
    # Lets grounding be scored for CORRECTNESS — right seed — not merely presence.
    expect_entities: list[str] = field(default_factory=list)
    # A question whose mention has NO referent in the graph ("dynamic pricing engine").
    # A good linker must ABSTAIN, not force a match — grounding one of these to a real
    # node is a false positive. This is what makes grounding *precision* measurable.
    should_not_ground: bool = False
    source_documents: list[str] = field(default_factory=list)


@dataclass
class QuestionResult:
    item: GoldItem
    vector_correct: bool
    hybrid_correct: bool
    graph_fact_recall: float           # hybrid only; fraction of expect_facts present
    hybrid_graph_facts: int            # how many graph facts the hybrid arm actually got
    grounded: bool                     # did the planner ground to the CORRECT node?
    grounded_to: list[str]             # what the planner actually produced (for the audit)
    ungrounded_recall: float           # graph-fact recall WITHOUT grounding (ablation)
    false_positive: bool               # negative question that grounded anyway (precision)
    vector_latency_ms: int
    hybrid_latency_ms: int
    # R12 candidate stage. `plan()` drops any name outside `candidates`, so the linker
    # cannot ground to what the candidate stage did not surface: candidate_hit is the
    # per-question ceiling on `grounded`. Recording both separates "linker chose wrong"
    # (candidate_hit and not grounded) from "linker never saw it" (not candidate_hit) —
    # opposite fixes, and indistinguishable from the grounding number alone.
    candidates: list[str] = field(default_factory=list)
    candidate_hit: bool = False        # was an acceptable entity offered to the planner?
    candidate_ms: int = 0              # embedding + store lookup
    plan_ms: int = 0                   # the planner LLM call
    error: str | None = None           # set if the question raised; excluded from scores


@dataclass
class StratumScore:
    stratum: str
    n: int = 0
    vector_correct: int = 0
    hybrid_correct: int = 0
    graph_fact_recall_sum: float = 0.0
    graph_fact_items: int = 0          # items in this stratum that declare expect_facts

    @property
    def graph_fact_recall(self) -> float | None:
        if self.graph_fact_items == 0:
            return None
        return self.graph_fact_recall_sum / self.graph_fact_items


def load_gold(path: Path) -> list[GoldItem]:
    items: list[GoldItem] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        items.append(
            GoldItem(
                id=d["id"],
                stratum=d["stratum"],
                question=d["question"],
                as_user=d["as"],
                expect_answer=d.get("expect_answer", []),
                forbid_answer=d.get("forbid_answer", []),
                expect_facts=d.get("expect_facts", []),
                expect_entities=d.get("expect_entities", []),
                should_not_ground=d.get("should_not_ground", False),
                source_documents=d.get("source_documents", []),
            )
        )
    return items


def _resolve_principal(conn: psycopg.Connection, name: str) -> Principal | None:
    row = conn.execute(
        "SELECT id, name, role, clearance FROM principal WHERE name ILIKE %s",
        (f"%{name}%",),
    ).fetchone()
    if not row:
        return None
    return Principal(id=row["id"], name=row["name"], role=row["role"], clearance=row["clearance"])


def _answer_correct(answer: Answer, item: GoldItem) -> bool:
    text = answer.text.lower()
    # A forbidden string present is an automatic fail — this is how the RBAC negative
    # test (X1) is scored: the secret must never appear, whatever else the answer says.
    if any(f.lower() in text for f in item.forbid_answer):
        return False
    # An empty expect_answer means "a correct answer asserts nothing specific" — used by
    # the refusal case, where passing the forbid check above is the whole test.
    return all(s.lower() in text for s in item.expect_answer)


def _graph_fact_recall(answer: Answer, item: GoldItem) -> float:
    """Fraction of the question's required edges that showed up in the graph context.

    A fact matches if some graph-fact line contains its subject, relation, and target
    tokens — matched on tokens, not exact arrow glyphs, so rendering can't break scoring.
    """
    if not item.expect_facts:
        return 0.0
    facts_lower = [f.lower() for f in answer.graph_facts]
    hits = 0
    for want in item.expect_facts:
        toks = [want["subject"].lower(), want["rel"].lower(), want["target"].lower()]
        if any(all(t in line for t in toks) for line in facts_lower):
            hits += 1
    return hits / len(item.expect_facts)


def _ground_with_retry(conn, driver, question, principal, *, temperature, retries=2):
    """Ground, retrying only the transient-infrastructure case: an empty candidate list.

    This is INFRASTRUCTURE RESILIENCE, not part of the retrieval algorithm — it changes
    no scoring rule and no grounding logic, it just re-attempts a call that failed for a
    reason outside the system under test. Local bge-m3 intermittently returns a NaN vector
    (Ollama HTTP 500) when embeds interleave with the cloud planner's calls; `vector_search`
    swallows that and returns no hits, so the candidate list comes back empty. In this
    corpus every question has readable chunks, so an empty candidate list is that fault, not
    a real result — and the exact same text embeds cleanly a moment later (verified: 0/30
    failures in isolation). A bounded retry with backoff recovers it and keeps runs
    reproducible; if it still fails, the caller's `unretrieved` handling excludes the
    question honestly rather than scoring it as a grounding miss.
    """
    g = ground(conn, driver, question, principal, temperature=temperature)
    for attempt in range(retries):
        if g.candidates:
            break
        time.sleep(1.0 * (attempt + 1))  # let the embedding service settle: 1s, then 2s
        g = ground(conn, driver, question, principal, temperature=temperature)
    return g


def evaluate(
    conn: psycopg.Connection, driver: Driver, gold: list[GoldItem]
) -> tuple[list[QuestionResult], dict[str, StratumScore]]:
    results: list[QuestionResult] = []
    scores: dict[str, StratumScore] = {s: StratumScore(stratum=s) for s in STRATUM_ORDER}

    for item in gold:
        principal = _resolve_principal(conn, item.as_user)
        if principal is None:
            raise ValueError(
                f"Gold item {item.id}: no principal matching '{item.as_user}'. Run: callosum init"
            )

        # One question that trips an LLM/embedding hiccup should not lose the other
        # nine. Record the error and press on; errored questions are reported but do
        # not count toward any stratum's score (they are neither pass nor fail).
        try:
            # Plan ONCE at temperature 0, grounded against the graph vocabulary, and hand
            # the identical plan to both arms — so the only difference between them is
            # whether graph facts are added, not which passages the planner fetched
            # (findings run 7). Synthesis pinned to temperature 0 for the same reason.
            grounding = _ground_with_retry(conn, driver, item.question, principal,
                                           temperature=0.0)
            shared = grounding.plan
            hybrid = ask(conn, driver, item.question, principal, use_graph=True,
                         plan_override=shared, synthesis_temperature=0.0)
            vector = ask(conn, driver, item.question, principal, use_graph=False,
                         plan_override=shared, synthesis_temperature=0.0)
        except Exception as exc:  # noqa: BLE001 — a harness must survive a flaky model
            results.append(
                QuestionResult(item, False, False, 0.0, 0, False, [], 0.0, False, 0, 0,
                               error=str(exc))
            )
            continue

        recall = _graph_fact_recall(hybrid, item)
        # Grounding CORRECTNESS: did the planner produce the right seed? If the gold item
        # names acceptable canonical entities, require one of them (a wrong seed that
        # happens to be in the vocab does NOT count). This separates a grounding error
        # (wrong seed) from a traversal bug (right seed, no facts) — distinct failures.
        if item.expect_entities:
            grounded = bool(set(shared.entities) & set(item.expect_entities))
        else:
            grounded = bool(shared.entities)

        # A negative question grounded to a real node is a FALSE POSITIVE — the linker
        # forced a match it should have refused. This is the precision side of grounding.
        false_positive = item.should_not_ground and bool(shared.entities)

        # Was the right answer even on the menu? Scored with the same "any one counts"
        # rule as `grounded`, so the two are directly comparable and candidate_hit is a
        # true upper bound: grounded implies candidate_hit, never the reverse. For a
        # negative question there is no acceptable entity by construction, so every
        # candidate offered is a distractor — the ceiling is not defined and we leave it
        # False rather than pretend the stage succeeded.
        if item.expect_entities:
            candidate_hit = bool(set(grounding.candidates) & set(item.expect_entities))
        else:
            candidate_hit = bool(grounding.candidates) and not item.should_not_ground

        # Ablation: what does the graph return WITHOUT grounding? Plan with no vocabulary
        # (raw mentions) and seed the traversal on them. No synthesis — recall is read off
        # graph_facts directly, so this is cheap. This is the "exact match only" baseline
        # that makes the grounding contribution a measured delta, not an assertion.
        ungrounded_recall = 0.0
        if item.expect_facts:
            raw = plan(item.question, temperature=0.0)  # deliberately no known_entities
            raw_facts, _ = graph_search(driver, raw.entities, principal)
            ungrounded_recall = _graph_fact_recall(
                Answer(text="", evidence=[], graph_facts=raw_facts, withheld=0, latency_ms=0),
                item,
            )

        qr = QuestionResult(
            item=item,
            vector_correct=_answer_correct(vector, item),
            hybrid_correct=_answer_correct(hybrid, item),
            graph_fact_recall=recall,
            hybrid_graph_facts=len(hybrid.graph_facts),
            grounded=grounded,
            grounded_to=list(shared.entities),
            ungrounded_recall=ungrounded_recall,
            false_positive=false_positive,
            vector_latency_ms=vector.latency_ms,
            hybrid_latency_ms=hybrid.latency_ms,
            candidates=list(grounding.candidates),
            candidate_hit=candidate_hit,
            candidate_ms=grounding.candidate_ms,
            plan_ms=grounding.plan_ms,
        )
        results.append(qr)

        sc = scores.setdefault(item.stratum, StratumScore(stratum=item.stratum))
        sc.n += 1
        sc.vector_correct += int(qr.vector_correct)
        sc.hybrid_correct += int(qr.hybrid_correct)
        if item.expect_facts:
            sc.graph_fact_items += 1
            sc.graph_fact_recall_sum += recall

    return results, scores


def grounding_traversal(results: list[QuestionResult]) -> dict | None:
    """Split the graph-dependent result into two stages (entity linking + traversal).

    The point of the split (per review): report the pipeline as two stages so the reader
    sees WHERE it fails. "Entity grounding 52% / traversal 100%" says the graph engine is
    correct and the linking stage is the bottleneck — a far stronger claim than a flat
    "multi-hop = 0%". Traversal accuracy is measured ONLY on questions that grounded, so
    it isolates the engine from the stage upstream of it.
    """
    all_graph_qs = [r for r in results if r.item.expect_facts and not r.error]
    if not all_graph_qs:
        return None

    # A question whose candidate stage returned NOTHING never entered the linking
    # pipeline — the planner had no vocabulary to ground against, so scoring it as a
    # grounding failure would blame the linker for an upstream miss. In this corpus every
    # question has readable public chunks, so an empty candidate list means retrieval
    # itself produced nothing; in the 2026-07-17 run these rows coincided exactly with the
    # Ollama embedding NaN (HTTP 500) logged at run start. The harness cannot always name
    # the cause, but it can honestly separate "never retrieved" from "retrieved and
    # mis-linked" and measure grounding only on the latter. `unretrieved` is reported as
    # its own count so the exclusion is visible, never silent (per review, 2026-07-17).
    graph_qs = [r for r in all_graph_qs if r.candidates]
    unretrieved = [r for r in all_graph_qs if not r.candidates]
    if not graph_qs:  # nothing was retrievable — the run is an infra artifact, not a result
        return {"n": len(all_graph_qs), "unretrieved": len(unretrieved),
                "evaluated": 0, "grounded": 0, "grounding_acc": None, "ger": None,
                "traversal_acc": None, "candidate_recall": None, "linker_acc": None,
                "loss_to_candidates": None, "loss_to_linker": None,
                "n_neg": 0, "n_neg_coref": 0, "false_positives": 0,
                "coref_false_positives": 0, "grounding_precision": None,
                "recall_grounded": None, "recall_ungrounded": None,
                "candidates_mean": 0.0, "candidates_max": 0,
                "candidate_ms_mean": 0.0, "plan_ms_mean": 0.0}

    grounded = [r for r in graph_qs if r.grounded]
    candidate_hits = [r for r in graph_qs if r.candidate_hit]

    # Negatives (should-not-ground) split by capability. An abstention negative ("dynamic
    # pricing engine") has NO referent in the graph — abstaining is pure linker precision.
    # A coreference negative ("the prior motion") is an unresolved REFERENCE; getting it
    # wrong is a missing coreference stage (M16), a different capability, and folding it
    # into precision would blame the linker for a gap it does not own (per review). Only
    # retrieved negatives count — an unretrieved one never reached the linker either.
    negatives = [r for r in results if r.item.should_not_ground and not r.error
                 and r.candidates and r.item.stratum != "coreference"]
    coref_negatives = [r for r in results if r.item.should_not_ground and not r.error
                       and r.candidates and r.item.stratum == "coreference"]
    false_pos = [r for r in negatives if r.false_positive]
    coref_false_pos = [r for r in coref_negatives if r.false_positive]
    # Latency and distractor load are properties of the candidate stage itself, which
    # runs for every question — including the negatives, where rejecting the whole list
    # is the work being measured. Scope them to retrieved, non-errored rows.
    scored = [r for r in results if not r.error and r.candidates]
    return {
        "n": len(all_graph_qs),
        "unretrieved": len(unretrieved),
        "evaluated": len(graph_qs),
        "grounded": len(grounded),
        "grounding_acc": len(grounded) / len(graph_qs),
        # Grounding Error Rate: fraction of mentions linked to the wrong node (or none),
        # over questions that were actually retrieved. This is the error source distinct
        # from a traversal bug — a wrong seed. As the graph grows and paraphrase gets
        # harder, GER is the number that will move first.
        "ger": (len(graph_qs) - len(grounded)) / len(graph_qs),
        # Mean recall among grounded questions: given the seed resolved, did the traversal
        # return the required edges? Undefined (—) if nothing grounded.
        "traversal_acc": (sum(r.graph_fact_recall for r in grounded) / len(grounded))
        if grounded else None,
        # Precision side: of the abstention negatives (no referent at all), how many did
        # the linker wrongly force onto a real node? A good linker abstains. Coreference
        # negatives are reported separately, not pooled in.
        "n_neg": len(negatives),
        "n_neg_coref": len(coref_negatives),
        "false_positives": len(false_pos),
        "coref_false_positives": len(coref_false_pos),
        "grounding_precision": (1 - len(false_pos) / len(negatives)) if negatives else None,
        # The ablation: mean graph-fact recall over graph questions, grounding ON vs OFF.
        # This is the headline delta — the graph engine is identical; only grounding moves.
        "recall_grounded": sum(r.graph_fact_recall for r in graph_qs) / len(graph_qs),
        "recall_ungrounded": sum(r.ungrounded_recall for r in graph_qs) / len(graph_qs),
        # R12: the candidate stage, reported as the ceiling it actually is.
        # candidate_recall is the fraction of graph questions where an acceptable entity
        # reached the planner at all. grounding_acc can never exceed it, so the gap
        # between them attributes the loss:
        #   1 - candidate_recall              -> candidate stage never surfaced it
        #   candidate_recall - grounding_acc  -> it was offered and the linker chose wrong
        # Only the second is an abstention/prompting problem. Tightening the linker
        # against the first would cut recall and leave the real cause untouched.
        "candidate_recall": len(candidate_hits) / len(graph_qs),
        "linker_acc": (len(grounded) / len(candidate_hits)) if candidate_hits else None,
        "loss_to_candidates": 1 - len(candidate_hits) / len(graph_qs),
        "loss_to_linker": (len(candidate_hits) - len(grounded)) / len(graph_qs),
        # Distractor load: how many names the linker must reject per question. Precision
        # is a function of this — an abstention rule that holds at 8 candidates may not
        # at 40, so the number has to travel with the precision figure to mean anything.
        "candidates_mean": (sum(len(r.candidates) for r in scored) / len(scored))
        if scored else 0.0,
        "candidates_max": max((len(r.candidates) for r in scored), default=0),
        # Latency, split by stage: candidate_ms is an embedding round-trip plus two store
        # queries, plan_ms is the planner LLM call. Which dominates decides whether the
        # lever is caching or prompt size.
        "candidate_ms_mean": (sum(r.candidate_ms for r in scored) / len(scored))
        if scored else 0.0,
        "plan_ms_mean": (sum(r.plan_ms for r in scored) / len(scored)) if scored else 0.0,
    }


CSV_COLUMNS = [
    "run", "model", "id", "stratum", "question",
    "expect_entities", "grounded_to", "grounded_correct", "false_positive",
    "candidate_hit", "candidate_count", "candidates",
    "candidate_ms", "plan_ms",
    "recall_grounded", "recall_ungrounded",
    "vector_correct", "hybrid_correct", "error",
]


def _csv_target(path: Path) -> Path:
    """Pick a log file whose header matches the columns we are about to write.

    The results log is append-only across runs and is the eval chapter's raw data: rows
    from run 7 have to still mean in run 14 what they meant when they were written. The
    R12 candidate columns change the schema, and appending wider rows under a narrower
    header would silently shift every field — the corruption would land in the history,
    not the new run, and nobody would notice until the numbers stopped adding up.

    So the log is versioned by schema rather than migrated: an existing file whose header
    no longer matches is left byte-for-byte alone, and this run goes to a sibling. Old
    runs stay readable under the schema that produced them, and each file stays valid CSV.
    Rewriting the old rows to fit the new schema would mean inventing candidate data for
    runs that never measured it — which is exactly the fabrication the handover forbids.
    """
    if not path.exists():
        return path
    with path.open("r", newline="", encoding="utf-8") as fh:
        existing = next(csv.reader(fh), None)
    if existing == CSV_COLUMNS:
        return path
    for version in itertools.count(2):
        candidate = path.with_name(f"{path.stem}-v{version}{path.suffix}")
        if not candidate.exists():
            return candidate
        with candidate.open("r", newline="", encoding="utf-8") as fh:
            if next(csv.reader(fh), None) == CSV_COLUMNS:
                return candidate
    raise AssertionError("unreachable")  # pragma: no cover


def write_csv(results: list[QuestionResult], path: Path, model: str) -> Path:
    """Append this run to a permanent, diffable experiment log (one row per question).

    Markdown tables are for reading; this CSV is for comparing run 7 → 8 → 9 → … without
    re-parsing prose. Each row carries what it grounded to and whether that was correct,
    so a regression in the linker is greppable, not buried in a report.

    Returns the path actually written, which is not always `path` — see `_csv_target`.
    """
    path = _csv_target(path)
    stamp = time.strftime("%Y-%m-%d %H:%M")
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(CSV_COLUMNS)
        for r in results:
            w.writerow([
                stamp, model, r.item.id, r.item.stratum, r.item.question,
                "|".join(r.item.expect_entities), "|".join(r.grounded_to),
                "" if not r.item.expect_facts else int(r.grounded),
                int(r.false_positive),
                # The candidate list is logged verbatim, not just its size: when the
                # linker false-positives, the row has to show WHICH distractor it was
                # offered ("dynamic pricing engine" -> was "Pricing Model B" the only
                # pricing-shaped name on the menu?). That is unrecoverable after the run.
                "" if not r.item.expect_facts else int(r.candidate_hit),
                len(r.candidates), "|".join(r.candidates),
                r.candidate_ms, r.plan_ms,
                f"{r.graph_fact_recall:.2f}" if r.item.expect_facts else "",
                f"{r.ungrounded_recall:.2f}" if r.item.expect_facts else "",
                int(r.vector_correct), int(r.hybrid_correct), r.error or "",
            ])
    return path


def render_markdown(
    results: list[QuestionResult], scores: dict[str, StratumScore], provider_note: str
) -> str:
    lines: list[str] = []
    lines.append("# Phase 7 evaluation — stratified, hybrid vs vector-only\n")
    lines.append(f"_Run: {time.strftime('%Y-%m-%d %H:%M')} · {provider_note}_\n")

    lines.append("## Score by stratum\n")
    lines.append("Read this table by row, not by total. The claim lives in the *shape*: "
                 "lookup ties, multi-hop separates.\n")
    lines.append("| Stratum | n | Vector-only correct | Hybrid correct | Graph-fact recall (hybrid) |")
    lines.append("|---|---|---|---|---|")
    for s in STRATUM_ORDER:
        sc = scores.get(s)
        if not sc or sc.n == 0:
            continue
        gr = sc.graph_fact_recall
        gr_cell = "—" if gr is None else f"{gr*100:.0f}%"
        lines.append(
            f"| {s} | {sc.n} | {sc.vector_correct}/{sc.n} | {sc.hybrid_correct}/{sc.n} | {gr_cell} |"
        )

    gt = grounding_traversal(results)
    if gt:
        ev = gt["evaluated"]
        lines.append("\n## Entity grounding vs traversal (graph-dependent questions)\n")
        lines.append("The multi-hop bottleneck is a Named Entity Linking problem, not a "
                     "graph one. This split shows which stage fails: the traversal engine "
                     "vs the linking of the question's words to a node name.\n")
        if gt["unretrieved"]:
            # State the exclusion up front — the reader must see that the algorithm
            # metrics below are over the retrieved subset, not the full question set.
            lines.append(f"**{gt['unretrieved']} of {gt['n']} graph questions returned no "
                         f"candidates and are excluded from the grounding metrics below** "
                         f"(the candidate stage produced nothing, so the linker was never "
                         f"exercised; in the 2026-07-17 run these were the embedding-NaN "
                         f"failures — an infrastructure fault, not a grounding result). "
                         f"All rates below are over the {ev} retrieved questions.\n")
        if ev == 0:
            lines.append("_No graph question was retrievable this run — grounding cannot be "
                         "scored. Fix the retrieval/embedding fault and rerun._\n")
            return "\n".join(lines) + "\n"
        trav = "—" if gt["traversal_acc"] is None else f"{gt['traversal_acc']*100:.0f}%"
        link = "—" if gt["linker_acc"] is None else f"{gt['linker_acc']*100:.0f}%"
        lines.append("| Stage | Accuracy (of retrieved) |")
        lines.append("|---|---|")
        # Ordered as the pipeline runs: candidates bound the linker, which bounds
        # traversal. Reading down the column localises the loss to a single stage.
        lines.append(f"| Candidate recall (right entity offered) | "
                     f"{gt['candidate_recall']*100:.0f}% "
                     f"({int(round(gt['candidate_recall']*ev))}/{ev}) |")
        lines.append(f"| Linker (given the entity was offered) | {link} |")
        lines.append(f"| Entity grounding (correct seed) | {gt['grounding_acc']*100:.0f}% "
                     f"({gt['grounded']}/{ev}) |")
        lines.append(f"| Grounding Error Rate (GER) | {gt['ger']*100:.0f}% |")
        if gt["grounding_precision"] is not None:
            lines.append(f"| Grounding precision — abstention negatives | "
                         f"{gt['grounding_precision']*100:.0f}% "
                         f"({gt['n_neg'] - gt['false_positives']}/{gt['n_neg']}) |")
        if gt["n_neg_coref"]:
            # Reported, not pooled: a coreference false-positive is a missing coref stage,
            # not a linker-abstention failure (per review, 2026-07-17).
            lines.append(f"| Coreference negatives resolved (separate capability) | "
                         f"{(gt['n_neg_coref'] - gt['coref_false_positives'])}/"
                         f"{gt['n_neg_coref']} |")
        lines.append(f"| Traversal (given grounding) | {trav} |")

        lines.append("\nGrounding is scored for CORRECTNESS (right seed), not mere presence. "
                     "Traversal is measured only on questions that grounded, so it isolates "
                     "the graph engine from the linking stage upstream. The `grounding_adv` "
                     "stratum is adversarial — paraphrases sharing no tokens with the node "
                     "name (\"metered billing\", \"pay-per-use\") — so grounding here tests "
                     "generalisation, not one lucky synonym. `grounding_neg` questions have "
                     "no referent in the graph; a good linker abstains (precision). "
                     "Coreference negatives (\"the prior motion\") are unresolved references, "
                     "a different capability (M16) — their misses are reported separately, "
                     "not folded into linker precision.\n")

        lines.append("\n### Where grounding loss comes from (R12)\n")
        lines.append(f"| Attribution | Share of {ev} retrieved graph questions |")
        lines.append("|---|---|")
        lines.append(f"| Lost — entity never offered to the planner | "
                     f"{gt['loss_to_candidates']*100:.0f}% |")
        lines.append(f"| Lost — entity offered, linker chose wrong | "
                     f"{gt['loss_to_linker']*100:.0f}% |")
        lines.append(f"| Grounded correctly | {gt['grounding_acc']*100:.0f}% |")
        lines.append(
            f"\nThe planner may only return names the candidate stage surfaced "
            f"(`retrieve.plan` drops the rest), so candidate recall is a hard ceiling on "
            f"grounding — the rows above split the GER into the stage that caused it. "
            f"Only *linker* loss is an abstention or prompting problem; *candidate* loss "
            f"needs a wider or better candidate stage, and tightening the linker would "
            f"make it worse. Distractor load: {gt['candidates_mean']:.1f} candidates per "
            f"question on average, {gt['candidates_max']} at most — precision is a "
            f"function of this, so it is not comparable across corpora of different size."
            f"\n\nStage latency: candidate {gt['candidate_ms_mean']:.0f} ms "
            f"(embedding + store lookup) · planner {gt['plan_ms_mean']:.0f} ms (LLM). "
            f"Both are per question and exclude synthesis.\n")

        # The ablation the reviewer asked for: identical graph engine, grounding on vs off.
        lines.append("\n## Ablation — grounding on vs off (identical graph engine)\n")
        lines.append("| Configuration | Graph-fact recall (graph questions) |")
        lines.append("|---|---|")
        lines.append(f"| Exact match only (no grounding) | {gt['recall_ungrounded']*100:.0f}% |")
        lines.append(f"| Planner grounding | {gt['recall_grounded']*100:.0f}% |")
        lines.append("\nSame traversal code, same corpus, same questions — the only variable "
                     "is whether the planner grounds the mention to a canonical node name. "
                     "The delta is the measured contribution of the grounding stage.\n")

    lines.append("\n## Per-question detail\n")
    lines.append("| id | stratum | sources | as | grounded | grounded to | vector | hybrid | graph facts | recall | question |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    tick = lambda b: "✓" if b else "✗"  # noqa: E731
    for r in results:
        sources = ", ".join(r.item.source_documents) or "-"
        if r.error:
            lines.append(
                f"| {r.item.id} | {r.item.stratum} | {sources} | {r.item.as_user} | — | — | "
                f"ERR | ERR | — | — | {r.item.question} (errored: {r.error[:60]}) |"
            )
            continue
        gr = "—" if not r.item.expect_facts else f"{r.graph_fact_recall*100:.0f}%"
        gnd = tick(r.grounded) if r.item.expect_facts else "—"
        # The mention→canonical audit: what the linker actually chose. For adversarial
        # rows this is the whole point — did "pay-per-use proposal" reach "Pricing Model B"?
        to = ", ".join(r.grounded_to) if (r.item.expect_facts and r.grounded_to) else "—"
        lines.append(
            f"| {r.item.id} | {r.item.stratum} | {sources} | {r.item.as_user} | {gnd} | {to} | "
            f"{tick(r.vector_correct)} | {tick(r.hybrid_correct)} | {r.hybrid_graph_facts} | "
            f"{gr} | {r.item.question} |"
        )

    lines.append("\n## How to read this\n")
    lines.append(
        "- **graph facts** is how many facts the hybrid arm actually received. When it is "
        "0 and the plan is shared, hybrid and vector-only see *identical* context — so any "
        "difference in their answers is model sampling noise (gpt-oss cloud ignores "
        "`temperature`), NOT the graph helping or hurting. Treat those rows as ties.\n"
        "- **Vector-only correct vs Hybrid correct**: equal on `lookup` is the expected "
        "tie; hybrid > vector on `relational`/`multi_hop` is the graph earning its keep.\n"
        "- **Graph-fact recall** is the mechanism check: it is the fraction of the "
        "question's required edges that reached the context. It is only meaningful for "
        "hybrid — vector-only has no graph context, so this column is graph-exclusive by "
        "construction.\n"
        "- **`rbac` rows** are pass/fail on the guardrail, not retrieval quality: X1 "
        "(investor) passes only if the secret never appears; X2 (founder) passes only if "
        "the authorised answer does.\n"
    )
    return "\n".join(lines) + "\n"
