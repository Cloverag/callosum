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

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
from neo4j import Driver

from callosum import store
from callosum.ontology import EntityType, RelationType
from callosum.retrieve import Answer, Principal, ask, graph_search, plan

STRATUM_ORDER = ["lookup", "relational", "multi_hop", "grounding_adv", "grounding_neg", "rbac"]


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

GOLD_ENTITIES = [
    ("Raj Malhotra", EntityType.PERSON, {"role": "CEO, co-founder"}),
    ("Priya Nair", EntityType.PERSON, {"role": "CFO"}),
    ("Marcus Webb", EntityType.PERSON, {"role": "Sequoia, board"}),
    ("Reject Pricing Model B", EntityType.DECISION, {"status": "rejected"}),
    ("Pricing Model B", EntityType.TOPIC, {}),
    ("Board Meeting 12", EntityType.MEETING, {}),
    ("Write pricing decision pack", EntityType.ACTION_ITEM, {"owner": "Priya Nair"}),
]

# All sourced from the board transcript (sensitivity 1 — an investor may read it).
GOLD_EDGES = [
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

# Sourced from the compensation review (sensitivity 3 — founder/exec only). This edge
# exists solely to exercise the graph-side RBAC gate: its quote embeds a salary, so if
# the path gate ever failed open, an investor asking about Priya would receive "$185K"
# through this edge — which is precisely the leak fixed in run 3. Seeding it makes the
# X1 rbac case a real test of the graph gate, not only the vector filter.
GOLD_CONFIDENTIAL_ENTITIES = [
    ("Meridian Inc", EntityType.ORGANIZATION, {}),
]
GOLD_CONFIDENTIAL_EDGES = [
    ("Priya Nair", RelationType.WORKS_AT, "Meridian Inc",
     "Priya Nair, CFO, is at $185K base"),
]


def seed_graph(conn: psycopg.Connection, driver: Driver) -> tuple[int, int]:
    """Write the gold graph directly, bypassing the LLM. Returns (edges, confidential).

    Requires the demo documents to already be ingested (chunks + embeddings in Postgres,
    Chunk nodes in Neo4j) — the seed attaches its edges to those real chunks so the
    sensitivity gate and citations work unchanged. It only replaces the *approval* step,
    not ingestion. MERGE-based writes make it idempotent: re-seeding is a no-op.
    """
    board = conn.execute(
        """
        SELECT c.id FROM chunk c JOIN document d ON d.id = c.document_id
        WHERE c.sensitivity = 1 ORDER BY c.ordinal LIMIT 1
        """
    ).fetchone()
    if not board:
        raise ValueError(
            "No sensitivity-1 chunk found. Ingest the board transcript first "
            "(scripts/eval.sh does this)."
        )
    board_chunk = str(board["id"])

    comp = conn.execute(
        "SELECT c.id FROM chunk c WHERE c.sensitivity = 3 ORDER BY c.ordinal LIMIT 1"
    ).fetchone()
    comp_chunk = str(comp["id"]) if comp else None

    def put_entity(name: str, etype: EntityType, attrs: dict, chunk_id: str) -> None:
        store.apply_entity(driver, {
            "name": name, "type": etype.value, "attributes": attrs, "chunk_id": chunk_id,
        })

    def put_edge(src: str, rel: RelationType, tgt: str, quote: str, chunk_id: str) -> None:
        store.apply_relationship(driver, {
            "source": src, "type": rel.value, "target": tgt,
            "quote": quote, "chunk_id": chunk_id,
        })

    # Entities before edges: apply_relationship MATCHes both endpoints, so the nodes
    # must exist first.
    for name, etype, attrs in GOLD_ENTITIES:
        put_entity(name, etype, attrs, board_chunk)
    for src, rel, tgt, quote in GOLD_EDGES:
        put_edge(src, rel, tgt, quote, board_chunk)

    confidential = 0
    if comp_chunk:
        for name, etype, attrs in GOLD_CONFIDENTIAL_ENTITIES:
            put_entity(name, etype, attrs, comp_chunk)
        for src, rel, tgt, quote in GOLD_CONFIDENTIAL_EDGES:
            put_edge(src, rel, tgt, quote, comp_chunk)
            confidential += 1

    return len(GOLD_EDGES), confidential


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


def evaluate(
    conn: psycopg.Connection, driver: Driver, gold: list[GoldItem]
) -> tuple[list[QuestionResult], dict[str, StratumScore]]:
    results: list[QuestionResult] = []
    scores: dict[str, StratumScore] = {s: StratumScore(stratum=s) for s in STRATUM_ORDER}

    # The graph's vocabulary, fetched once — the planner grounds each question's entities
    # against it (entity linking). This is what makes "usage-based pricing" reach the
    # "Pricing Model B" node instead of seeding on nothing.
    vocabulary = set(store.entity_names(driver))

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
            shared = plan(item.question, known_entities=sorted(vocabulary), temperature=0.0)
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
            grounded = bool(set(shared.entities) & vocabulary)

        # A negative question grounded to a real node is a FALSE POSITIVE — the linker
        # forced a match it should have refused. This is the precision side of grounding.
        false_positive = item.should_not_ground and bool(set(shared.entities) & vocabulary)

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
    graph_qs = [r for r in results if r.item.expect_facts and not r.error]
    if not graph_qs:
        return None
    grounded = [r for r in graph_qs if r.grounded]
    negatives = [r for r in results if r.item.should_not_ground and not r.error]
    false_pos = [r for r in negatives if r.false_positive]
    return {
        "n": len(graph_qs),
        "grounded": len(grounded),
        "grounding_acc": len(grounded) / len(graph_qs),
        # Grounding Error Rate: fraction of mentions linked to the wrong node (or none).
        # This is the error source distinct from a traversal bug — a wrong seed. As the
        # graph grows and paraphrase gets harder, GER is the number that will move first.
        "ger": (len(graph_qs) - len(grounded)) / len(graph_qs),
        # Mean recall among grounded questions: given the seed resolved, did the traversal
        # return the required edges? Undefined (—) if nothing grounded.
        "traversal_acc": (sum(r.graph_fact_recall for r in grounded) / len(grounded))
        if grounded else None,
        # Precision side: of the questions with no valid referent, how many did the
        # linker wrongly force onto a real node? A good linker abstains.
        "n_neg": len(negatives),
        "false_positives": len(false_pos),
        "grounding_precision": (1 - len(false_pos) / len(negatives)) if negatives else None,
        # The ablation: mean graph-fact recall over graph questions, grounding ON vs OFF.
        # This is the headline delta — the graph engine is identical; only grounding moves.
        "recall_grounded": sum(r.graph_fact_recall for r in graph_qs) / len(graph_qs),
        "recall_ungrounded": sum(r.ungrounded_recall for r in graph_qs) / len(graph_qs),
    }


def write_csv(results: list[QuestionResult], path: Path, model: str) -> None:
    """Append this run to a permanent, diffable experiment log (one row per question).

    Markdown tables are for reading; this CSV is for comparing run 7 → 8 → 9 → … without
    re-parsing prose. Each row carries what it grounded to and whether that was correct,
    so a regression in the linker is greppable, not buried in a report.
    """
    import csv

    stamp = time.strftime("%Y-%m-%d %H:%M")
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow([
                "run", "model", "id", "stratum", "question",
                "expect_entities", "grounded_to", "grounded_correct", "false_positive",
                "recall_grounded", "recall_ungrounded",
                "vector_correct", "hybrid_correct", "error",
            ])
        for r in results:
            w.writerow([
                stamp, model, r.item.id, r.item.stratum, r.item.question,
                "|".join(r.item.expect_entities), "|".join(r.grounded_to),
                "" if not r.item.expect_facts else int(r.grounded),
                int(r.false_positive),
                f"{r.graph_fact_recall:.2f}" if r.item.expect_facts else "",
                f"{r.ungrounded_recall:.2f}" if r.item.expect_facts else "",
                int(r.vector_correct), int(r.hybrid_correct), r.error or "",
            ])


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
        lines.append("\n## Entity grounding vs traversal (graph-dependent questions)\n")
        lines.append("The multi-hop bottleneck is a Named Entity Linking problem, not a "
                     "graph one. This split shows which stage fails: the traversal engine "
                     "vs the linking of the question's words to a node name.\n")
        trav = "—" if gt["traversal_acc"] is None else f"{gt['traversal_acc']*100:.0f}%"
        lines.append("| Stage | Accuracy |")
        lines.append("|---|---|")
        lines.append(f"| Entity grounding (correct seed) | {gt['grounding_acc']*100:.0f}% "
                     f"({gt['grounded']}/{gt['n']}) |")
        lines.append(f"| Grounding Error Rate (GER) | {gt['ger']*100:.0f}% |")
        if gt["grounding_precision"] is not None:
            lines.append(f"| Grounding precision (abstains on negatives) | "
                         f"{gt['grounding_precision']*100:.0f}% "
                         f"({gt['n_neg'] - gt['false_positives']}/{gt['n_neg']}) |")
        lines.append(f"| Traversal (given grounding) | {trav} |")
        lines.append("\nGrounding is scored for CORRECTNESS (right seed), not mere presence. "
                     "Traversal is measured only on questions that grounded, so it isolates "
                     "the graph engine from the linking stage upstream. The `grounding_adv` "
                     "stratum is adversarial — paraphrases sharing no tokens with the node "
                     "name (\"metered billing\", \"pay-per-use\") — so grounding here tests "
                     "generalisation, not one lucky synonym. `grounding_neg` questions have "
                     "no referent in the graph; a good linker abstains (precision).\n")

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
    lines.append("| id | stratum | as | grounded | grounded to | vector | hybrid | graph facts | recall | question |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    tick = lambda b: "✓" if b else "✗"  # noqa: E731
    for r in results:
        if r.error:
            lines.append(
                f"| {r.item.id} | {r.item.stratum} | {r.item.as_user} | — | — | "
                f"ERR | ERR | — | — | {r.item.question} (errored: {r.error[:60]}) |"
            )
            continue
        gr = "—" if not r.item.expect_facts else f"{r.graph_fact_recall*100:.0f}%"
        gnd = tick(r.grounded) if r.item.expect_facts else "—"
        # The mention→canonical audit: what the linker actually chose. For adversarial
        # rows this is the whole point — did "pay-per-use proposal" reach "Pricing Model B"?
        to = ", ".join(r.grounded_to) if (r.item.expect_facts and r.grounded_to) else "—"
        lines.append(
            f"| {r.item.id} | {r.item.stratum} | {r.item.as_user} | {gnd} | {to} | "
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
