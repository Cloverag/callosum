"""Retrieval: plan → search both stores → filter by permission → merge → answer.

The permission filter is not a post-processing step. It is pushed down into the
SQL WHERE clause and the Cypher WHERE clause, so a chunk the caller may not read
is never fetched, never ranked, and never sits in memory next to the prompt. An
investor asking "why did we reject Pricing Model B?" does not load the salary
discussion — not because we drop it afterwards, but because we never selected it.

Filtering after retrieval would be one bug away from leaking. This is the only
placement that actually satisfies the PRD's RBAC requirement.
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import psycopg
from neo4j import Driver
from pydantic import BaseModel, Field

from callosum.llm import embed, structured, text as generate


@dataclass
class Principal:
    """Who is asking. Everything downstream is scoped by this."""

    id: uuid.UUID | None
    name: str
    role: str        # founder | exec | employee | investor | advisor
    clearance: int   # 0 public .. 4 restricted


@dataclass
class Evidence:
    chunk_id: uuid.UUID
    document_title: str
    text: str
    source: str      # "graph" | "vector"
    score: float = 0.0


@dataclass
class Answer:
    text: str
    evidence: list[Evidence]
    graph_facts: list[str]
    withheld: int    # chunks the permission filter refused. Surfaced, not hidden.
    latency_ms: int
    plan: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


class Plan(BaseModel):
    entities: list[str] = Field(
        default_factory=list,
        description="Named entities or topics to look up in the graph, exactly as a "
                    "document would name them (e.g. 'Pricing Model B', not 'pricing').",
    )
    needs_graph: bool = Field(
        description="True if the question is about relationships, ownership, approval, "
                    "history, or causation — anything of the form 'who/when/why did X'."
    )
    needs_vector: bool = Field(
        description="True if answering requires the content of documents rather than "
                    "just the shape of the relationships between them."
    )
    search_query: str = Field(
        description="The text to embed for semantic search. Usually the question itself, "
                    "rephrased into the vocabulary a board document would use."
    )


PLANNER_PROMPT = """\
You route questions about a startup's institutional memory to the right stores.

There are two:
- A **knowledge graph** of people, decisions, meetings, topics, action items and
  metrics, connected by edges like APPROVED, OPPOSED, SUPERSEDES, MADE_IN, OWNS.
  It answers "how are these related?" — who approved a decision, which meeting it
  was made in, what superseded it, who owns the follow-up.
- A **vector store** of document chunks. It answers "what does the text actually
  say?" — rationale, discussion, nuance, anything you have to read to know.

Most real questions need both. "Why did we reject Pricing Model B?" needs the graph
to find the decision and the people who took positions on it, and the vector store
to recover the reasoning they gave. Prefer both unless one is clearly useless.

Extract entity names as a document would write them — "Pricing Model B", not
"the pricing model" — because the graph is keyed on exact names.
"""


def plan(question: str) -> Plan:
    return structured(PLANNER_PROMPT, question, Plan)


# ---------------------------------------------------------------------------
# Search — both halves push the permission predicate into the query itself
# ---------------------------------------------------------------------------


def vector_search(
    conn: psycopg.Connection, query: str, principal: Principal, k: int = 8
) -> tuple[list[Evidence], int]:
    """Semantic search, scoped to what this caller may read.

    Returns (hits, withheld). We run the same search twice — once with the clearance
    predicate and once without — purely so we can *tell the caller how many results
    were withheld*. Reporting "2 sources withheld" is a feature: it tells a founder
    that a fuller answer exists, without leaking what it says.
    """
    vector = embed([query], input_type="query")[0]

    hits = conn.execute(
        """
        SELECT c.id, c.text, d.title, 1 - (c.embedding <=> %s::vector) AS score
        FROM chunk c
        JOIN document d ON d.id = c.document_id
        WHERE c.sensitivity <= %s
        ORDER BY c.embedding <=> %s::vector
        LIMIT %s
        """,
        (vector, principal.clearance, vector, k),
    ).fetchall()

    blocked = conn.execute(
        """
        SELECT count(*) AS n FROM (
            SELECT c.id FROM chunk c
            WHERE c.sensitivity > %s
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
        ) t
        """,
        (principal.clearance, vector, k),
    ).fetchone()

    evidence = [
        Evidence(
            chunk_id=row["id"],
            document_title=row["title"],
            text=row["text"],
            source="vector",
            score=float(row["score"]),
        )
        for row in hits
    ]
    return evidence, int(blocked["n"])


def graph_search(
    driver: Driver, entities: list[str], principal: Principal, max_hops: int = 2
) -> tuple[list[str], list[uuid.UUID]]:
    """Traverse from named entities, up to `max_hops` away. Returns (facts, chunk ids).

    This is the half of the system that vectors cannot do. "Why did we reject Pricing
    Model B?" needs to connect the *decision* to the *people who took positions on it*
    — and person→decision is two hops from the topic (Person -POSITION-> Decision
    -ABOUT-> Topic). A one-hop search off "Pricing Model B" finds the ABOUT edge and
    stops; the founder's real question ("who opposed it, who made the call") lives one
    hop further out. Bounded multi-hop is what turns the graph from a lookup table into
    a reasoning surface — and it is the comparison the thesis rests on.

    RBAC is enforced per edge, fail-closed, over the WHOLE path. Every relationship on
    a returned path is gated by the sensitivity of the chunk it was *extracted from*
    (`r.chunk_id` → that Chunk's sensitivity). `all(... WHERE exists { readable src })`
    means a path is returned only if *every* edge on it is readable: one confidential
    hop withholds the entire path — not the relation, not the endpoint names, and above
    all not `r.quote`, which can embed confidential text verbatim (a benign WORKS_AT
    edge carried "$185K base" and leaked a salary to an investor before edge-gating
    existed; see docs/findings.md). Multi-hop widens the blast radius — a two-hop path
    is two chances to leak — so the gate is on the path, not a post-filter.

    `r.chunk_id IS NOT NULL` guards edges with no recorded source: an edge we cannot
    attribute to a readable chunk is treated as unreadable. Fail-closed is the only
    safe default for an access-control filter.
    """
    if not entities:
        return [], []

    # max_hops is interpolated into the query (Neo4j cannot parameterise the bound of
    # a variable-length pattern), so it must never be attacker-influenced text. It is
    # an int argument set by us; clamp it to a sane range and hard-fail anything else.
    if not isinstance(max_hops, int) or not 1 <= max_hops <= 3:
        raise ValueError(f"max_hops must be an int in 1..3, got {max_hops!r}")

    facts: list[str] = []
    seen_facts: set[str] = set()
    chunk_ids: list[uuid.UUID] = []

    # Every edge on a returned path must be readable, or the whole path is withheld.
    # We express this by unwinding the path's edges, left-joining each to its source
    # chunk, and keeping the path only if the count of *readable* source chunks equals
    # the number of edges. A missing chunk (OPTIONAL MATCH -> null) or one above the
    # caller's clearance fails the count, so it fails closed. This avoids nesting an
    # EXISTS subquery inside a list predicate, which is brittle across Neo4j 5.x points.
    cypher = f"""
        MATCH (seed:Entity)
        WHERE seed.name IN $names
        MATCH path = (seed)-[rels*1..{max_hops}]-(other:Entity)
        WITH path, rels
        UNWIND rels AS r
        OPTIONAL MATCH (src:Chunk {{id: r.chunk_id}})
        WITH path, rels,
             count(r) AS edge_count,
             sum(CASE WHEN src IS NOT NULL AND src.sensitivity <= $clearance
                      THEN 1 ELSE 0 END) AS readable_edges
        WHERE readable_edges = edge_count
        RETURN [n IN nodes(path)         | n.name]           AS node_names,
               [r IN relationships(path) | type(r)]          AS rel_types,
               [r IN relationships(path) | startNode(r).name] AS rel_starts,
               [r IN relationships(path) | r.quote]          AS rel_quotes,
               [r IN relationships(path) | r.chunk_id]       AS rel_chunks,
               length(path)                                  AS hops
        ORDER BY hops ASC
        LIMIT 100
    """

    with driver.session() as session:
        result = session.run(cypher, names=entities, clearance=principal.clearance)

        for record in result:
            names = record["node_names"]
            rels = record["rel_types"]
            starts = record["rel_starts"]
            quotes = record["rel_quotes"]
            chunks = record["rel_chunks"]

            # Decompose the path into atomic, deduplicated edge facts. The same edge
            # shows up on many paths; the LLM should see it once.
            for i, rel in enumerate(rels):
                a, b = names[i], names[i + 1]
                subject, obj = (a, b) if starts[i] == a else (b, a)
                fact = f"{subject} —{rel}→ {obj}"
                if quotes[i]:
                    fact += f'  (evidence: "{quotes[i]}")'
                if fact not in seen_facts:
                    seen_facts.add(fact)
                    facts.append(fact)
                if chunks[i]:
                    chunk_ids.append(uuid.UUID(chunks[i]))

            # For genuine multi-hop paths, also surface the chain itself — this is the
            # connection a vector search cannot make, and the thing worth showing the
            # LLM (and the examiner) as the graph earning its keep.
            if len(rels) >= 2:
                chain = _render_chain(names, rels, starts)
                if chain not in seen_facts:
                    seen_facts.add(chain)
                    facts.append(chain)

    return facts, chunk_ids


def _render_chain(names: list[str], rels: list[str], starts: list[str]) -> str:
    """Render a path as a directed chain, e.g.
    `path: Marcus —ATTENDED→ Board Meeting 12 ←MADE_IN— Reject Model B`."""
    out = names[0]
    for i, rel in enumerate(rels):
        a, b = names[i], names[i + 1]
        if starts[i] == a:            # edge points a -> b, same as our walk direction
            out += f" —{rel}→ {b}"
        else:                          # edge points b -> a, against our walk direction
            out += f" ←{rel}— {b}"
    return "path: " + out


def fetch_chunks(
    conn: psycopg.Connection, chunk_ids: list[uuid.UUID], principal: Principal
) -> list[Evidence]:
    """Resolve graph-discovered chunk ids to text — again, only what the caller may read."""
    if not chunk_ids:
        return []

    rows = conn.execute(
        """
        SELECT c.id, c.text, d.title
        FROM chunk c
        JOIN document d ON d.id = c.document_id
        WHERE c.id = ANY(%s) AND c.sensitivity <= %s
        """,
        (list(set(chunk_ids)), principal.clearance),
    ).fetchall()

    return [
        Evidence(chunk_id=r["id"], document_title=r["title"], text=r["text"], source="graph")
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------


ANSWER_PROMPT = """\
You answer questions about a startup's institutional memory.

You are given two kinds of context, and they play different roles:

**Graph facts** are structured relationships extracted from company documents and
approved by a human — who proposed a decision, who opposed it, which meeting it was
made in, what it superseded. Treat these as authoritative. They are why this system
exists: they let you say "Raj approved it" without guessing.

**Source passages** are the actual text of the documents. Use them for rationale,
nuance, and quotation. Every claim you make should be traceable to one of them.

Rules:
- Cite sources inline as [1], [2] matching the numbered passages. Every substantive
  claim needs a citation.
- If the context does not answer the question, say so plainly. Do not fill the gap
  from general knowledge — a fabricated board decision is worse than no answer,
  because the founder will act on it.
- When the question is about a decision, structure the answer around: what was
  decided, why, who supported it, who opposed it, who made the final call, and what
  action items came out of it. That is the shape founders actually need.
- If sources were withheld for permission reasons, you will be told the count. Say
  that the answer may be incomplete. Never speculate about what was withheld.
"""


def ask(
    conn: psycopg.Connection, driver: Driver, question: str, principal: Principal,
    *, use_graph: bool = True,
) -> Answer:
    """Answer a question for a principal.

    `use_graph=False` ablates the knowledge graph entirely — retrieval falls back to
    pure vector search. This is not a runtime feature; it exists so the Phase 7 eval
    can run the identical question under hybrid and vector-only conditions and measure
    what the graph actually contributes per question type. The whole thesis is that the
    two conditions tie on lookup and diverge on multi-hop; this switch is how we show it.
    """
    started = time.monotonic()

    p = plan(question)

    graph_facts: list[str] = []
    graph_chunk_ids: list[uuid.UUID] = []
    if use_graph and p.needs_graph:
        graph_facts, graph_chunk_ids = graph_search(driver, p.entities, principal)

    evidence: list[Evidence] = []
    withheld = 0
    # In the ablation (use_graph=False) vector always runs — otherwise a question the
    # planner routed graph-only would hand vector-only an empty context for the wrong
    # reason, and the comparison would flatter the graph. Vector-only must genuinely
    # get its best shot at every question.
    if p.needs_vector or not use_graph:
        # A graph-routed question can come back with an empty search_query; fall back to
        # the raw question so the ablation still searches for something real (and so we
        # never embed an empty string). The question is always a usable query.
        query_text = p.search_query.strip() or question
        evidence, withheld = vector_search(conn, query_text, principal)

    # The merge: graph-discovered passages joined with semantically-similar ones,
    # deduplicated on chunk id. Both halves have already been permission-filtered.
    seen = {e.chunk_id for e in evidence}
    for ev in fetch_chunks(conn, graph_chunk_ids, principal):
        if ev.chunk_id not in seen:
            evidence.append(ev)
            seen.add(ev.chunk_id)

    context = _render(graph_facts, evidence, withheld)
    answer_text = generate(ANSWER_PROMPT, f"{context}\n\nQuestion: {question}")

    answer = Answer(
        text=answer_text,
        evidence=evidence,
        graph_facts=graph_facts,
        withheld=withheld,
        latency_ms=int((time.monotonic() - started) * 1000),
        plan=p.model_dump(),
    )
    _log(conn, question, principal, answer)
    return answer


def _render(graph_facts: list[str], evidence: list[Evidence], withheld: int) -> str:
    parts = []

    if graph_facts:
        parts.append("## Graph facts (human-approved)\n" + "\n".join(f"- {f}" for f in graph_facts))

    if evidence:
        passages = [
            f"[{i}] {e.document_title}\n{e.text}"
            for i, e in enumerate(evidence, start=1)
        ]
        parts.append("## Source passages\n" + "\n\n".join(passages))

    if withheld:
        parts.append(
            f"## Access note\n{withheld} source(s) matched this question but are above "
            "your clearance and were not retrieved. The answer may be incomplete."
        )

    return "\n\n".join(parts) if parts else "No context available."


def _log(conn: psycopg.Connection, question: str, principal: Principal, answer: Answer) -> None:
    """Every query is logged. This doubles as the eval set: question, what was
    retrieved, what was said. Phase 7 measures hybrid vs vector-only against it."""
    import json

    conn.execute(
        """
        INSERT INTO query_log (principal_id, question, plan, graph_hits, vector_hits,
                               denied_count, answer, latency_ms)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            principal.id,
            question,
            json.dumps(answer.plan),
            json.dumps(answer.graph_facts),
            json.dumps([str(e.chunk_id) for e in answer.evidence]),
            answer.withheld,
            answer.text,
            answer.latency_ms,
        ),
    )
