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

import anthropic
import psycopg
from neo4j import Driver
from pydantic import BaseModel, Field

from meridian.config import SYNTHESIS_MODEL, settings
from meridian.ingest import embed


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
    client = anthropic.Anthropic(api_key=settings().anthropic_api_key or None)
    response = client.messages.parse(
        model=SYNTHESIS_MODEL,
        max_tokens=1024,
        output_config={"effort": "low"},  # routing is not the hard part
        system=PLANNER_PROMPT,
        messages=[{"role": "user", "content": question}],
        output_format=Plan,
    )
    return response.parsed_output


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
    driver: Driver, entities: list[str], principal: Principal
) -> tuple[list[str], list[uuid.UUID]]:
    """Traverse from named entities. Returns (human-readable facts, supporting chunk ids).

    The chunk ids coming back are the bridge in action: a graph hit hands us the
    exact passages that justify it, which we then pull from Postgres as citations.
    """
    if not entities:
        return [], []

    facts: list[str] = []
    chunk_ids: list[uuid.UUID] = []

    with driver.session() as session:
        result = session.run(
            """
            MATCH (e:Entity)
            WHERE e.name IN $names
            MATCH (e)-[r]-(other:Entity)
            OPTIONAL MATCH (c:Chunk)-[:MENTIONS]->(e)
            WHERE c.sensitivity <= $clearance
            RETURN e.name   AS subject,
                   e.type   AS subject_type,
                   type(r)  AS rel,
                   startNode(r).name = e.name AS outgoing,
                   other.name AS object,
                   other.type AS object_type,
                   r.quote  AS quote,
                   collect(DISTINCT c.id) AS chunks
            LIMIT 100
            """,
            names=entities,
            clearance=principal.clearance,
        )

        for record in result:
            if record["outgoing"]:
                fact = f"{record['subject']} —{record['rel']}→ {record['object']}"
            else:
                fact = f"{record['object']} —{record['rel']}→ {record['subject']}"
            if record["quote"]:
                fact += f'  (evidence: "{record["quote"]}")'
            facts.append(fact)

            for cid in record["chunks"]:
                if cid:
                    chunk_ids.append(uuid.UUID(cid))

    return facts, chunk_ids


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
    conn: psycopg.Connection, driver: Driver, question: str, principal: Principal
) -> Answer:
    started = time.monotonic()

    p = plan(question)

    graph_facts: list[str] = []
    graph_chunk_ids: list[uuid.UUID] = []
    if p.needs_graph:
        graph_facts, graph_chunk_ids = graph_search(driver, p.entities, principal)

    evidence: list[Evidence] = []
    withheld = 0
    if p.needs_vector:
        evidence, withheld = vector_search(conn, p.search_query, principal)

    # The merge: graph-discovered passages joined with semantically-similar ones,
    # deduplicated on chunk id. Both halves have already been permission-filtered.
    seen = {e.chunk_id for e in evidence}
    for ev in fetch_chunks(conn, graph_chunk_ids, principal):
        if ev.chunk_id not in seen:
            evidence.append(ev)
            seen.add(ev.chunk_id)

    context = _render(graph_facts, evidence, withheld)

    client = anthropic.Anthropic(api_key=settings().anthropic_api_key or None)
    response = client.messages.create(
        model=SYNTHESIS_MODEL,
        max_tokens=4000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=ANSWER_PROMPT,
        messages=[{"role": "user", "content": f"{context}\n\nQuestion: {question}"}],
    )
    text = next((b.text for b in response.content if b.type == "text"), "")

    answer = Answer(
        text=text,
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
