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
from callosum.retrieve import Answer, Principal, ask

STRATUM_ORDER = ["lookup", "relational", "multi_hop", "rbac"]


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


@dataclass
class QuestionResult:
    item: GoldItem
    vector_correct: bool
    hybrid_correct: bool
    graph_fact_recall: float           # hybrid only; fraction of expect_facts present
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
            hybrid = ask(conn, driver, item.question, principal, use_graph=True)
            vector = ask(conn, driver, item.question, principal, use_graph=False)
        except Exception as exc:  # noqa: BLE001 — a harness must survive a flaky model
            results.append(QuestionResult(item, False, False, 0.0, 0, 0, error=str(exc)))
            continue

        recall = _graph_fact_recall(hybrid, item)
        qr = QuestionResult(
            item=item,
            vector_correct=_answer_correct(vector, item),
            hybrid_correct=_answer_correct(hybrid, item),
            graph_fact_recall=recall,
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

    lines.append("\n## Per-question detail\n")
    lines.append("| id | stratum | as | vector | hybrid | graph-fact recall | question |")
    lines.append("|---|---|---|---|---|---|---|")
    tick = lambda b: "✓" if b else "✗"  # noqa: E731
    for r in results:
        if r.error:
            lines.append(
                f"| {r.item.id} | {r.item.stratum} | {r.item.as_user} | "
                f"ERR | ERR | — | {r.item.question} (errored: {r.error[:60]}) |"
            )
            continue
        gr = "—" if not r.item.expect_facts else f"{r.graph_fact_recall*100:.0f}%"
        lines.append(
            f"| {r.item.id} | {r.item.stratum} | {r.item.as_user} | "
            f"{tick(r.vector_correct)} | {tick(r.hybrid_correct)} | {gr} | {r.item.question} |"
        )

    lines.append("\n## How to read this\n")
    lines.append(
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
