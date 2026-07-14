# Callosum — Institutional Memory

A continuously evolving AI knowledge layer for a startup's organizational memory. It
captures documents, decisions, discussions, ownership and business context, then lets
an LLM **retrieve and reason over** them instead of guessing.

> Named for the *corpus callosum*, the fibre bundle that joins the brain's two
> hemispheres. This system has two hemispheres too — a knowledge graph and a vector
> store — and the bridge between them is the whole idea.

The question the whole system exists to answer:

> **"Why did we reject Pricing Model B?"**
>
> → who proposed it, who supported it, who opposed it, in which meeting, what the
> rationale was, what action items came out of it — and the sources, so a founder can
> verify every claim.

![Architecture](docs/architecture.png)

## Why not one database

| Store | Answers | Cannot answer |
|---|---|---|
| SQL | "What meetings happened in Q2?" | Deep relationship traversal — the joins explode |
| Vector DB | "What text is semantically similar?" | "**How** are these entities related?" |
| Knowledge graph | "Who approved this, via which meeting?" | "What does this 20-page PDF actually say?" |

So we use all three, joined. **That is the thesis.**

### The bridge

A chunk row in Postgres and its `(:Chunk)` node in Neo4j share one UUID:

```
(:Chunk)-[:MENTIONS]->(:Decision)-[:MADE_IN]->(:Meeting)<-[:ATTENDED]-(:Person)
```

So a **vector hit can traverse into the graph**, and a **graph hit can pull back the
exact passage that proves it**. Bidirectional. That is what makes this a hybrid system
rather than two systems bolted together.

## Two invariants

**1. The permission filter runs *before* retrieval, not after.** It is pushed down into
the SQL `WHERE` and the Cypher `WHERE`, so a chunk the caller may not read is never
fetched, never ranked, and never sits in memory next to the prompt. An investor asking
about pricing does not load the salary discussion — not because we drop it afterwards,
but because we never selected it.

**2. The LLM never writes to the graph.** It *proposes*, into `proposed_change`. A human
approves, and only then does memory mutate, with a version row appended. Every proposed
relationship carries a **verbatim quote** from the source text; no quote, no edge.

This is the project's answer to PRD Open Question #3 — *"How much autonomy should AI have
before requiring founder approval?"* Our answer: **none for writes.**

## Stack

- **Postgres 16 + pgvector** — raw documents, chunk embeddings, RBAC, version history
- **Neo4j 5** — the knowledge graph
- **Claude Opus 4.8** — entity/relationship extraction and grounded synthesis
- **Voyage** — 1024-dim embeddings
- Python 3.12, FastAPI, Typer

Extraction quality *is* graph quality — a missed `OPPOSED` edge is a wrong answer — so
Opus runs on both extraction and synthesis. Cost is controlled with prompt caching and
the Batch API, not with a weaker model.

## Quickstart

```bash
docker compose up -d                     # Postgres + Neo4j
uv venv --python 3.12 && uv pip install -e .
cp .env.example .env                     # add ANTHROPIC_API_KEY + VOYAGE_API_KEY

callosum init
callosum ingest-doc data/demo/board_meeting_12_transcript.txt --type transcript --sensitivity 1
callosum ingest-doc data/demo/compensation_review_CONFIDENTIAL.txt --type transcript --sensitivity 3

callosum pending                         # what Claude proposed, with confidence scores
callosum approve --all                   # commit to the graph

callosum query "Why did we reject Pricing Model B?" --as Raj
callosum query "What is Priya's compensation?" --as Marcus   # withheld — investor clearance
```

Neo4j Browser: <http://localhost:7474> (`neo4j` / `callosum123`) → `MATCH (n) RETURN n`

## Status

| Phase | State |
|---|---|
| 1. Ingestion — load, dedupe, chunk, embed | built |
| 2. Extraction — entities + relationships, with evidence quotes | built |
| 3. Storage — Postgres + Neo4j joined on shared UUIDs | built |
| 4. Retrieval — plan → graph ‖ vector → permission filter → merge → answer | built |
| 5. Memory update — approval queue, versioning | built |
| 6. Frontend — founder chat, approval queue, graph viewer | not started |
| 7. Evaluation — hybrid vs. vector-only retrieval benchmark | not started |

Phases 1–5 have never been run end-to-end against live APIs. Expect bugs on first run.

## Known limitations

- **Entity resolution is exact-string-match.** "Raj" and "Raj Malhotra" become two nodes.
  Real resolution (aliases, embedding-similarity blocking) is future work.
- **RBAC is a flat clearance ladder**, not a role hierarchy with inheritance.
- **No real-time transcription, no Slack/Gmail/Zoom connectors.** Deliberately out of
  scope — every one of these is a "V2" item in the source PRD.

## Provenance

Requirements are derived from a product assignment by
[@Devguru-codes](https://github.com/Devguru-codes/meridian_pre_intern_work) — a PRD, use
cases, and a static HTML mockup. That repo contains **no backend and no engineering**;
this repository is the system his document describes.
