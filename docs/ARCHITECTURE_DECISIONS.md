# Architecture Decision Records (ADRs)

Short records of *why* major structural choices were made, so the reasoning survives
past the session that made it. Format per record: Decision · Alternatives · Why · Status.
Status is **Accepted** (implemented + in `master`) or **Proposed** (design-only, not built).

---

## ADR-001 — Two stores bridged by a shared chunk UUID
**Decision:** Postgres (records, vectors, RBAC, versions) + Neo4j (entity graph), joined by
a chunk UUID that Postgres mints and Neo4j reuses as a `(:Chunk)` node id.
**Alternatives:** single Postgres with `pgvector` + recursive CTEs for graph; single graph DB.
**Why:** vector recall and bounded multi-hop reasoning are different access patterns; one
UUID lets a vector hit walk into the graph and a graph hit fetch exact source text. Neither
store does both well alone — this bridge *is* the thesis.
**Status:** Accepted.

## ADR-002 — Tenant isolation via database RLS, not application-only filtering (Postgres)
**Decision:** Postgres Row-Level Security (`ENABLE`+`FORCE`) with a `tenant_isolation` policy
keyed on a session GUC (`app.workspace_id`).
**Alternatives:** add `WHERE workspace_id = ?` in every query (application-only).
**Why:** application-only filtering is one forgotten `WHERE` from a cross-tenant leak. RLS
makes isolation the database's job — fail-closed by default, enforced even for queries that
forget to filter.
**Status:** Accepted.

## ADR-003 — A non-superuser runtime role + two-DSN split
**Decision:** app connects as `callosum_app` (`NOSUPERUSER NOBYPASSRLS`, `postgres_app_dsn`);
migrations/admin use the `callosum` superuser (`postgres_dsn`).
**Alternatives:** run everything as the superuser created by `POSTGRES_USER`.
**Why:** **superusers bypass RLS unconditionally — `FORCE` cannot stop them.** RLS was silently
a no-op until the app stopped connecting as a superuser. This was the single most important
correctness fix in P1.
**Status:** Accepted.

## ADR-004 — Neo4j tenant isolation via entity-identity partitioning + query predicates
**Decision:** `workspace_id` is part of entity identity (`MERGE (e:Entity {name,type,workspace_id})`)
plus a workspace predicate on every graph read (seed gate, `readable_edges` path gate,
`entity_names_for_chunks`).
**Alternatives:** rely only on per-query `WHERE` predicates; per-workspace Neo4j databases
(Enterprise edition).
**Why:** Neo4j Community has no RLS, so isolation is query-level and fragile. A shared entity
node (same name across tenants) can't be fixed by a `WHERE` — the *node* is the leak. Baking
`workspace_id` into identity physically partitions the graph, so a colliding name can never
bridge two tenants; the query predicates are defence-in-depth on top.
**Status:** Accepted.

## ADR-005 — Deterministic frozen evaluation as the acceptance gate
**Decision:** the retrieval eval runs against a **seeded gold graph** (no LLM); the gated
metrics are **candidate recall** and **traversal-given-grounding**. LLM grounding metrics are
recorded but do not gate.
**Alternatives:** end-to-end answer-correctness as the gate.
**Why:** the hosted planner LLM is nondeterministic even at temp 0 (429s, sampling), so answer
text can't be a stable gate. Retrieval metrics are deterministic and are exactly what a schema
change (e.g. RLS) could regress — so they're the honest security/quality gate.
**Status:** Accepted. (A cleaner *split* — deterministic security eval fully separated from the
LLM eval — is Proposed in ADR-008-adjacent work / issue #10.)

## ADR-006 — Verified provenance; the research core is frozen
**Decision:** no graph edge exists without its verbatim evidence quote found in the source;
every write is provenance-stamped; the research engine (`store.py`/`retrieve.py` extraction,
verifier, planner, RBAC) is frozen behind `eval-baseline-v3`.
**Alternatives:** trust extractor output; allow ongoing edits to the core.
**Why:** the contribution is *verified* KG construction, not GraphRAG. Freezing prevents
silent regressions; the only sanctioned exception (tenancy) must reproduce `eval-baseline-v3`
exactly — predicates can only remove rows, so single-tenant behaviour is provably unchanged.
**Status:** Accepted.

## ADR-007 — Alembic for product-domain schema migrations
**Decision:** introduce Alembic (`meridian/migrations/`, single linear chain `0001→0005`) for
all post-freeze schema change; the frozen `schema/postgres.sql` remains the base schema.
**Alternatives:** keep hand-run raw SQL scripts.
**Why:** tenancy needed reversible, ordered, reviewable schema change across many tables; raw
scripts have no ordering or rollback. Alembic keeps one source of truth per table.
**Status:** Accepted.

## ADR-008 — Postgres as single source of truth, Neo4j a rebuildable projection
**Decision (proposed):** make Postgres canonical; `store.approve()` writes Postgres-first, then
projects to Neo4j; add a `rebuild-graph` command that replays approved changes → Neo4j.
**Alternatives:** current dual-write; full CQRS / event-sourcing with a message bus.
**Why:** the graph is already derived from approved `proposed_change` rows and `seed-eval`
already rebuilds deterministically, so this mostly *formalizes* an existing property and makes
graph inconsistency self-healing — **without** a message queue (which would add failure modes
for little V1 gain).
**Status:** Proposed — design-only, tracked in issue #10. Not built. Do not implement before P2
planning and only after evidence justifies it.
