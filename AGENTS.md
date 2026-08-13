# Callosum contributor guide

## Purpose and current state

Callosum is an institutional-memory prototype for startup decisions. It ingests source
documents, creates **verified** graph proposals, requires a human to approve each
proposal, and answers questions with a hybrid of vector retrieval and graph traversal.
The two stores are deliberately coupled: Postgres owns documents, chunk text,
embeddings, RBAC, history, and the approval queue; Neo4j owns entities and their
relationships. A `chunk.id` UUID exists in both stores and is the bridge between them.

The repository is a Python 3.12 CLI application. Phases 1–5 are implemented, but the
README explicitly says they have not been exercised end-to-end against live APIs. The
frontend is not implemented. Evaluation has a deterministic seeded graph, while normal
ingestion/extraction remains model-driven.

The source code and schema are authoritative when they disagree with older prose or
recorded outputs. In particular, the active Ollama default in `config.py` and
`.env.example` is `gpt-oss:120b-cloud`; some documentation still refers to Kimi.

## Meridian product context

Callosum originated as the technical foundation for **Meridian**, an AI-first board
operating system for founder-led companies from pre-seed through Series B. The original
product discovery defined the real problem as workflow continuity—not merely scheduling
or storing board files. Founders typically assemble board work from Drive, email, Notion,
Slack, Zoom, and DocuSign. That stack fragments documents, decisions, approvals, and
follow-up; it forces repeated context reconstruction and makes strategic decisions hard
to retrieve, verify, or execute months later.

The intended Meridian product lifecycle is: plan a meeting → create/review an agenda and
board pack → publish a permissioned pre-read → run the meeting with grounded context →
review decisions and minutes → convert approved decisions into owned commitments → track
execution → retrieve history for the next meeting. Callosum provides the trustworthy
memory layer in that lifecycle: raw source retention, source-backed graph proposals,
human approval, hybrid graph/vector retrieval, and pre-retrieval RBAC. It does **not**
yet provide the workspace, meeting, agenda, board-pack, resolution, external action,
or integration capabilities of Meridian. A foundational Next.js frontend shell exists,
starting with the Entity Conflict resolution UI.

Product priorities from the original research are:

1. **Foundation / V1:** secure workspace, board preparation, agenda and pack review,
   live contextual assistance, decision/minutes review, and institutional memory.
2. **V2:** resolution policy, follow-up, and the bridge from approved decisions to
   measurable execution.
3. **V3:** cross-module context, natural-language knowledge search at scale, proactive
   risk signals, and evidence-backed recommendations.

The product must remain startup-first: simple, self-serve, integrated with mature
external tools, and focused on saving founder time while improving governance quality.
It must not claim to replace cap-table products, project-management products, or legal
governance systems. AI may draft, retrieve, summarize, and recommend; it may not silently
approve a fact, vote, resolution, owner, deadline, external message, signature, task, or
memory update. See `PRD.md` for the complete requirements and `ROADMAP.md` for the
authoritative sequential delivery gates and current progress status.

## Architecture

```text
source file (TXT/MD/VTT/PDF/DOCX)
  -> ingest.load -> content hash -> offset-preserving paragraph chunks -> embeddings
  -> Postgres: document + chunk rows                 -> Neo4j: matching (:Chunk) nodes
  -> LLM structured extraction -> evidence verifier
       -> verified entities/edges: Postgres proposed_change (pending)
       -> rejected edges: Postgres extraction_failure (quarantine)
  -> human approval -> Neo4j Entity / relationship + Postgres node_version

question + principal
  -> planner (canonical entity grounding) -> vector search AND bounded graph traversal
  -> each store enforces clearance before returning results
  -> merge graph facts and readable source chunks -> grounded LLM answer -> query_log
```

### Data ownership and bridge

| Concern | Postgres + pgvector | Neo4j |
|---|---|---|
| Source of truth | Raw documents, chunks, embeddings, permissions, approvals, versions, audits | No raw source text |
| Graph content | Pending mutations and provenance | `(:Entity)` nodes and approved relationship edges |
| Cross-store identity | Postgres creates the chunk UUID | `(:Chunk {id})` uses that same UUID |
| Provenance route | `document.raw_text` and chunk offsets | edge `chunk_id` -> `(:Chunk)` -> Postgres chunk |

Graph edges have `quote` and `chunk_id`. A graph result can therefore recover the exact
readable chunk; a vector result can follow `Chunk -[:MENTIONS]-> Entity` into the graph.

### Security and provenance invariants

1. **No LLM write path exists.** Extraction only inserts `proposed_change` records.
   `store.approve()` is the only normal graph mutation path. Do not bypass it for product
   behavior; `evaluate.seed_graph()` is the deliberately declared evaluation-only exception.
2. **No relationship without a verified contiguous quote.** `extract.verify()` requires
   non-empty evidence, distinct endpoints, emitted endpoints, and a `locate()` match in
   the source chunk. It tolerates only whitespace/case/typographic punctuation changes.
   Paraphrases and stitched quotes are failures, not approximations.
3. **Never discard a rejected extraction.** Every failed relationship must be recorded in
   `extraction_failure` with its reason and provenance stamp.
4. **Permission filtering is query-time and fail-closed.** SQL filters chunk sensitivity
   before ranking; Cypher requires every edge in a returned path to resolve to a readable
   source chunk. Do not move either filter after retrieval or make missing edge provenance
   readable.
5. **The chunk span must be exact.** For every `Chunk`,
   `raw_text[start_char:end_char] == chunk.text`. Quote spans are converted to absolute
   document offsets when proposals are queued.
6. **Embeddings are 1024 dimensions.** The schema's `VECTOR(1024)` and both providers
   depend on it. Switching embedding providers requires re-embedding the corpus even if
   dimensions match.
7. **Approved graph writes are replay-safe.** The graph is written first with `MERGE`, then
   the Postgres proposal is marked approved. Preserve that order because the stores have no
   distributed transaction.

## Repository map

### Root and runtime configuration

| Path | Responsibility |
|---|---|
| `README.md` | Product thesis, setup, commands, and stated limitations/status. Useful orientation; validate operational details against source/config. |
| `CONTRIBUTING.md` | Contribution policy. Declares the pipeline core frozen pending measured evaluation evidence; prioritizes frontend, corpus/eval data, traceability, and approval UX. |
| `AGENTS.md` | This implementation-oriented guidance for future agents and contributors. |
| `pyproject.toml` | Packaging, Python constraint (`>=3.12,<3.13`), dependencies, `callosum` console entry point, pytest marker/default selection, Hatch build configuration. |
| `.env.example` | Copy to `.env` for provider and database settings. Contains no secrets; `.env` is ignored. |
| `.gitignore` | Excludes local environment/build artifacts, `reference/`, generated graph outputs, and generated `eval/results.md`. |
| `docker-compose.yml` | Local Postgres 16 + pgvector on host `5433`, and Neo4j 5 on `7474`/`7687`; mounts the schema only on fresh Postgres volume initialization. |

### Application package: `src/callosum/`

| Path | Responsibility |
|---|---|
| `__init__.py` | Package identity and version (`0.1.0`). |
| `config.py` | Pydantic settings loaded from `.env`, provider enum, endpoints/model defaults, chunk sizing, and the shared embedding dimension constant. `settings()` is cached. |
| `ontology.py` | Versioned Pydantic extraction contract: entity/relation/status/failure enums and `Entity`, `Relationship`, `Extraction` models. Bump `ONTOLOGY_VERSION` for semantic ontology changes and update the changelog. |
| `llm.py` | Provider boundary. Implements schema flattening/validation, structured generation, free-form answer synthesis, 1024-dimension embeddings, recoverable Ollama errors, and provider health checks. No other module should call vendor SDKs directly. |
| `ingest.py` | Loads supported file formats, computes SHA-256 dedupe hashes, makes overlapping paragraph/sentence chunks with true character offsets, and verifies/locates evidence quotes. Re-exports `llm.embed`. |
| `extract.py` | Holds the extraction prompt/version, invokes structured extraction, verifies every relation, stamps provenance, and offers Anthropic batch submit/collect. It proposes; it never writes to Neo4j. |
| `store.py` | Database integration. Owns Postgres transactions, document/chunk/proposal/failure queries, Neo4j constraints and bridge nodes, approved entity/edge writes, and idempotent approval sequencing. |
| `retrieve.py` | Planner, canonical entity grounding, permission-filtered vector and graph search, graph-chunk resolution, context rendering, LLM answer synthesis, and query audit logging. It includes the graph-vs-vector ablation hook used only by evaluation. |
| `evaluate.py` | Deterministic gold graph seed, JSONL gold-set loader, hybrid/vector-only evaluation, grounding/traversal metrics, append-only CSV recording, and Markdown results rendering. |
| `cli.py` | Typer interface for health checking, initialization, ingest, approval review/commit, query, Anthropic batch collection, gold seeding, evaluation, and failure reporting. |

### Frontend Application: `frontend/`

| Path | Responsibility |
|---|---|
| `src/app/` | Next.js App Router providing the Meridian shell (Sidebar, Header, Layout) and feature pages (e.g., `entity-conflicts`). |
| `src/app/globals.css` | Implements the **Cinematic Luxury Aesthetic**: deep void/slate dark modes, premium off-white light modes, semantic CSS variables for `next-themes`, and glassmorphic utilities. |
| `src/components/` | Reusable UI components. Heavily relies on Framer Motion for micro-interactions (e.g., fluid layout animations, theme toggling) and `lucide-react` for iconography. |
| `src/lib/api.ts` | The typed API client layer. Currently implements in-memory mock endpoints with simulated latency; designed to be swapped for real backend integration in P1. |

### Persistence: `schema/`

| Path | Responsibility |
|---|---|
| `schema/postgres.sql` | Initial Postgres schema. Defines clearance ladder, principals/ACL grants, source documents, vector chunks, append-only versions, pending proposals, extraction quarantine, and query logs. Also creates pgvector/HNSW indexes. Changing it requires migration/rebuild planning because Compose only runs it on a fresh volume. |

Key tables:

- `sensitivity`, `principal`, `acl_grant`: access-control model; current retrieval uses the numeric clearance ladder.
- `document`, `chunk`: durable source and embeddings. `chunk.sensitivity` is intentionally denormalized for the hot permission predicate.
- `proposed_change`, `extraction_failure`: reviewable extraction outcome and experimental data.
- `node_version`: append-only approval history snapshot.
- `query_log`: audit trail and source of future analysis.

### Documentation: `docs/`

| Path | Responsibility |
|---|---|
| `docs/architecture.md` | Mermaid system/retrieval/memory-update diagrams and design rationale. |
| `docs/architecture.png` | Rendered architecture image displayed by the README. |
| `docs/findings.md` | Research/evaluation log and the rationale for the freeze boundary, grounding stage, RBAC gate, and corpus-growth roadmap. Read before proposing core changes. |
| `docs/ontology-changelog.md` | Version history for ontology semantics. Current source declares version 2, adding `REQUESTED`. |

### Datasets and evaluation: `data/` and `eval/`

| Path | Responsibility |
|---|---|
| `data/demo/board_meeting_12_transcript.txt` | Pricing-rejection and stance/polarity demo corpus. |
| `data/demo/board_meeting_13_transcript.txt` | Later pricing reversal corpus; exercises `SUPERSEDES`, temporal reasoning, and `REQUESTED`. |
| `data/demo/compensation_review_CONFIDENTIAL.txt` | Sensitivity-3 corpus used to prove both vector and graph RBAC behavior. |
| `eval/gold.jsonl` | Versioned JSONL questions with expected/forbidden answer fragments, graph facts, canonical entity targets, and negative-grounding cases. Strata: lookup, relational, multi-hop, temporal, grounding adversarial/negative, and RBAC. |
| `eval/results.csv` | Append-only historical per-question run log. Do not overwrite it; each evaluation appends rows. |

### Automation and tests

| Path | Responsibility |
|---|---|
| `scripts/demo.sh` | Destructive local demo: resets Docker volumes, performs ordinary model extraction, reviews failures, approves all, and asks two queries. |
| `scripts/eval.sh` | Destructive reproducible evaluation: resets volumes, ingests without extraction, seeds the declared gold graph, then runs the benchmark. |
| `tests/test_pipeline.py` | Fast deterministic coverage of chunk/quote offsets, graph-chain rendering, gold graph/question consistency, verification/quarantine behavior, and evaluator scoring. |
| `tests/test_extraction.py` | Live-provider LLM regression tests for polarity, recall floor, supersession, boilerplate restraint, and quarantine. Marked `llm`, excluded from normal pytest runs. |

## Operational workflows

### Local setup and safe checks

```bash
docker compose up -d
uv venv --python 3.12
uv pip install -e .
cp .env.example .env
ollama signin
ollama pull bge-m3
callosum doctor
callosum init
pytest -q
```

On Windows, invoke the shell scripts through a Bash-capable environment. Both scripts
run `docker compose down -v`; they delete local database volumes. Never run them against
anything whose local data must be kept.

### Normal ingestion and review

```bash
callosum ingest-doc path/to/file.txt --type transcript --sensitivity 1
callosum pending
callosum failures
callosum approve <id>          # preferred review path
# `callosum approve --all` is a demo shortcut, not a production review workflow
callosum query "Why did we reject Pricing Model B?" --as "Raj Malhotra"
```

Supported inputs are PDF, DOCX, TXT, Markdown, and VTT. Ingestion is idempotent by
content hash: an identical document is deliberately skipped. `--batch` is Anthropic-only;
`--no-extract` stores chunks/embeddings but leaves the graph for `seed-eval`.

### Evaluation protocol

Use `bash scripts/eval.sh` for the comparable baseline. It performs a deterministic
retrieval experiment, not an extraction-quality experiment:

1. Ingest documents with `--no-extract`.
2. Seed `evaluate.GOLD_GROUPS` into Neo4j as a declared gold graph.
3. For every JSONL item, calculate one temperature-0 plan and reuse it for hybrid and
   vector-only arms.
4. Score answer fragments/forbidden fragments, graph-fact recall, grounding correctness,
   false-positive grounding, and no-grounding traversal recall.

`eval/results.md` is generated and ignored; `eval/results.csv` is the persistent log.
Do not claim an improvement from a single answer anecdote. Report the relevant stratum,
the graph-fact mechanism measure, provider/model, corpus, and baseline comparison.

## Change rules

### Do

- Add corpus documents and paired gold questions across strata; maintain a clear
  source-to-gold trace and extend the capability matrix rather than adding duplicate data.
- Write deterministic tests for all changes to parsing, offsets, schema, evaluation logic,
  or access control. Run `pytest -q`; deliberately run `pytest -m llm` only with a
  configured live provider and when the cost/nondeterminism is acceptable.
- Keep provider access behind `llm.py`, typed extraction behind `ontology.py`, and Postgres
  storage operations behind `store.py`. **A new Neo4j operation goes through the gateway
  `graph.py`, not `store.py`** (owner's decision 2026-08-13, `rules.md` §3): `store.py` is
  frozen and `graph.py` is not, so routing a new product write through `store.py` turns a
  product feature into a frozen-core edit and gains nothing. The `FROZEN_ALLOWLIST` in
  `tests/test_no_raw_cypher.py` grandfathers pre-existing sites pending migration — it only
  shrinks, and new work does not join it.
- Stamp extraction proposals and failures with provider, model, prompt, and ontology
  versions. Bump the relevant version when changing prompt or ontology semantics.
- Preserve compatibility between `RelationType`, the extractor prompt, gold seed data,
  evaluation expectations, and Neo4j relationship validation.
- Treat permission tests as security tests; validate both vector and graph sides whenever
  RBAC, chunk provenance, Cypher, or retrieval merge behavior changes.
- Add any web/frontend code as an isolated package/layer over existing functions; do not
  make it part of the frozen core unless measurement justifies it.

### Do not

- Do not modify `ingest.py`, `extract.py`, `retrieve.py`, `store.py`, or
  `schema/postgres.sql` merely to make code look cleaner. The documented freeze boundary
  requires a measured shortcoming and an evaluation result.
- Do not permit model output to write Neo4j directly, auto-approve changes, or silently
  drop unverified relationships.
- Do not weaken `locate()` into fuzzy semantic matching. Its narrow tolerance protects
  provenance; paraphrases are failures.
- Do not remove the SQL/Cypher clearance predicates, filter after ranking/traversal, or
  return a path with an edge missing `chunk_id`. A confidential quote on an otherwise
  benign relation is still confidential.
- Do not interpolate unsanitized values into Cypher. Relationship type interpolation is
  safe only because `store.apply_relationship()` validates it against `RelationType`;
  `max_hops` is likewise constrained to 1–3.
- Do not mutate, truncate, or replace historical `eval/results.csv`, quarantine rows, or
  version history to make results look better.
- Do not use `approve --all` as the assumed workflow for sensitive documents.
- Do not use a different embedding dimension without a schema migration and full
  re-embedding.

## Known technical limits and active research risks

- Entity resolution is exact `(name, type)` matching; aliases and same-name people can
  collapse or split incorrectly.
- Planner grounding currently passes all graph names to the LLM. This is suitable for the
  small demo graph, not a large vocabulary; future candidate retrieval must be evaluated.
- The grounder has a documented precision failure: it may force a pricing-adjacent term to
  `Pricing Model B` instead of abstaining. `grounding_neg` measures this explicitly.
- The corpus is still synthetic/small. Board Meeting 12 tests polarity; Meeting 13 tests
  temporal reversal. The findings document identifies aliasing, conflicting evidence, and
  contextual references as future corpus capabilities.
- A foundational Next.js frontend exists, but full workspace data integration, real-time transcription, role inheritance, robust entity resolution, and automatic migration frameworks do not yet exist.
- `acl_grant` exists in the schema as an escape hatch, but the current retrieval predicates
  use clearance only. Do not state that per-object ACL grants are enforced until the query
  paths actually incorporate them.
- Generated documentation has historical naming/date inconsistencies. Record the exact
  commit, model, configuration, and date for any new findings instead of silently editing
  history.

## Before handing off a change

1. Check `git diff` and confirm only intended files changed.
2. Run the fast test suite; include the command/result in the handoff.
3. For a schema/config/provider change, verify `callosum doctor` against a fresh local
   environment when practical.
4. For core retrieval/extraction changes, run the documented eval baseline and compare the
   appropriate stratum and mechanism metrics with the prior CSV rows.
5. For RBAC changes, prove both that a high-clearance principal receives authorized source
   text and that a low-clearance principal cannot receive it through vectors, graph facts,
   graph quotes, or graph-resolved chunks.
