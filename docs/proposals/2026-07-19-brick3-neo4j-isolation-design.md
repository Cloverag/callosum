# Brick 3 — Neo4j workspace isolation (P1 design)

**Status:** proposed · **Date:** 2026-07-19 · **Owner:** Raghav
**Depends on:** Brick 2b (Postgres RLS) complete & verified (eval 21/21)
**Frozen-core:** yes — sanctioned tenancy exception (edits `store.py` + `retrieve.py`); single-tenant behaviour must stay byte-identical, proven by re-running `eval-baseline-v3`.

---

## 1. Why Neo4j needs its own brick

Brick 2b locked **Postgres** per workspace with Row-Level Security. But the system is *two* stores bridged by a shared chunk UUID:

```
vector hit  -> chunk id -> (:Chunk) -> MENTIONS -> (:Entity) -> traverse edges
```

The graph half lives in Neo4j, and **Neo4j Community Edition has no Row-Level Security.** There is no `FORCE`, no policy, no session predicate the database enforces for us. Isolation in Neo4j can only be **query-level**: every Cypher statement that reads tenant data must *itself* carry a `workspace_id` predicate. A single forgotten predicate is a cross-tenant leak.

So Brick 3 is inherently more fragile than Brick 2b, and the design is built to remove the fragility rather than rely on discipline.

## 2. The crux: entity nodes are currently shared across tenants

This is the one thing that makes Neo4j isolation different from "just add a WHERE clause."

Today, `apply_entity` does:

```cypher
MERGE (e:Entity {name: $name, type: $type})
```

`MERGE` on `{name, type}` means **"Raj Patel / PERSON" is a single node no matter who ingested it.** Under multi-tenancy that node would be shared by every workspace that ever mentioned a "Raj Patel" — and because `graph_search` seeds directly on entity *name*:

```cypher
MATCH (seed:Entity) WHERE seed.name IN $names        -- bypasses Chunk entirely
```

…workspace A traversing from "Raj Patel" would walk straight into workspace B's edges hanging off the same shared node. **A per-query WHERE clause cannot fix a shared node** — the node itself is the leak.

**Decision: `workspace_id` becomes part of entity identity.**

```cypher
MERGE (e:Entity {name: $name, type: $type, workspace_id: $workspace_id})
```

Now "Raj Patel" in workspace A is a *different node* from "Raj Patel" in workspace B. The graph is physically partitioned by tenant; a colliding name can no longer bridge two customers. This is the structural backbone of the brick — the WHERE predicates below are defence-in-depth on top of it, not the primary mechanism.

## 3. Where `workspace_id` lives

| Element | Carries `workspace_id`? | How |
|---|---|---|
| `(:Chunk)` node | ✅ property | mirrors Postgres; Chunk is the bridge and already carries `sensitivity` |
| `(:Entity)` node | ✅ **part of MERGE identity** | see §2 — partitions the graph |
| `[:MENTIONS]`, `[:REL]` edges | ✅ via source chunk | every edge already records `r.chunk_id`; we gate through `Chunk.workspace_id`, reusing the proven `readable_edges` path gate |

Edges are scoped **through their source chunk**, not a duplicated `r.workspace_id`, because (a) the sensitivity gate already works exactly this way, so we extend one `CASE` instead of inventing a parallel mechanism, and (b) an edge whose source chunk is in another workspace is exactly an edge we must not traverse — the existing "unattributable edge = unreadable" fail-closed rule already covers the null case.

## 4. Write path — stamp on the way in (all in `store.py`)

Each write helper gains a required `workspace_id` argument. Fail-closed: no default, so a caller that forgets it is a hard error, not a silent Default-Workspace write.

- **`upsert_chunk_node`** → `SET c.workspace_id = $workspace_id` (alongside `sensitivity`).
- **`apply_entity`** → `MERGE (e:Entity {name, type, workspace_id})`; the `MATCH (c:Chunk {id})` for the MENTIONS edge additionally requires `c.workspace_id = $workspace_id`.
- **`apply_relationship`** → both `MATCH (:Entity {name, workspace_id})` endpoints are workspace-scoped, and the edge records `r.chunk_id` as today (its workspace is enforced at read time via the chunk).

**Constraints** (`ensure_constraints`): the Entity uniqueness constraint moves from `(name, type)` to **`(name, type, workspace_id)`**. Chunk stays keyed on its globally-unique `id`. Add an index on `(:Chunk workspace_id)` and `(:Entity workspace_id)` for seed-scan performance.

## 5. Read path — scope every tenant query (all in `retrieve.py` / `store.py`)

- **`entity_names_for_chunks`** — add `AND c.workspace_id = $workspace_id` to the existing `WHERE c.id IN $ids AND c.sensitivity <= $clearance`.
- **`graph_search`**:
  - **Seed gate:** `MATCH (seed:Entity) WHERE seed.name IN $names AND seed.workspace_id = $workspace_id`.
  - **Path gate:** extend the `readable_edges` sum so an edge counts as readable only when its source chunk is *both* clearance-OK *and* in-workspace:
    ```cypher
    sum(CASE WHEN src IS NOT NULL
             AND src.sensitivity <= $clearance
             AND src.workspace_id = $workspace_id
             THEN 1 ELSE 0 END) AS readable_edges
    WHERE readable_edges = edge_count      -- one out-of-tenant edge withholds the whole path
    ```
- **`entity_names`** (global vocabulary) — admin/eval only; document that it is **not** a runtime path. Optionally add a workspace-scoped overload; do not call it from the query flow.

## 6. How `workspace_id` reaches these functions

Postgres uses a session GUC (`SET app.workspace_id`). **Neo4j has no session equivalent** — the value must be passed as an explicit Cypher parameter on every call. So the retrieval entry point resolves the caller's workspace once and threads it as a parameter into `graph_search` / `entity_names_for_chunks` (the same place `principal.clearance` already flows). Threading it as a required parameter — rather than a hidden default — is what makes a missing scope a loud failure.

## 7. Backfill (existing single-tenant graph)

Neo4j has no Alembic. A one-time, idempotent Cypher migration stamps the Default Workspace onto the current graph:

```cypher
MATCH (c:Chunk)  WHERE c.workspace_id IS NULL SET c.workspace_id = $default;
MATCH (e:Entity) WHERE e.workspace_id IS NULL SET e.workspace_id = $default;
```

Shipped as a small Meridian-owned script (`meridian/migrations/neo4j/0001_backfill_workspace.py` or a `callosum`-adjacent admin command). For the eval harness this is moot — `eval_tenant.sh` reseeds a fresh graph, so writes stamp Default from the start.

## 8. Frozen-core justification (single-tenant no-op)

Everything here either (a) adds a predicate that can only *remove* rows, or (b) adds `workspace_id` to entity identity. Under a single tenant, **every** node carries the same Default Workspace id, so:
- every predicate (`= Default`) matches every row → no rows removed;
- `MERGE {name, type, Default}` partitions into exactly one partition → identical to today's `MERGE {name, type}`.

Therefore single-tenant retrieval must be byte-identical. **Proof obligation:** re-run `eval-baseline-v3` via `scripts/eval_tenant.sh`; candidate recall must stay **21/21** and traversal **100%**. Any drift = stop.

## 9. Sub-brick plan (one reviewable change per commit)

Mirrors the Brick 2b cadence — implement, verify, commit, repeat. Nothing stacks on an unverified change.

- **3.1 — Write-side + identity + constraints.** Stamp `workspace_id` on chunk/entity/edge writes; move Entity identity to `(name,type,workspace_id)`; update constraints; backfill Default. *No read scoping yet.* Verify: existing suites green, eval unchanged. Commit.
- **3.2 — Read-side scoping.** Add the workspace predicates to `entity_names_for_chunks` + `graph_search` (seed + path gate); thread `workspace_id` through the retrieval entry point. Verify: Default path works, eval unchanged. Commit.
- **3.3 — Break-in tests (the security proof).** Two workspaces, **deliberately colliding entity names**. Assert: A's `graph_search` never returns B's edges/entities even on an identical name; a path that would only connect *through* a shared name does **not** connect; `entity_names_for_chunks` is workspace-scoped; a no-workspace call returns nothing. Commit.
- **3.4 — Frozen evaluation.** `scripts/eval_tenant.sh`; require candidate recall 21/21 + traversal 100% (record grounding/429s as observed, per the 2b.5 rule). On pass → **Brick 3 complete → P1 complete.** Commit.

## 10. Threats specifically re-checked here

- **T-colliding-name:** same entity name in two workspaces → must be two nodes, never one (§2). Primary break-in test.
- **T-seed-bypass:** seeding on `Entity.name` skips Chunk → seed gate + entity identity both scope it (§5, §2).
- **T-path-bridge:** a multi-hop path that leaves the tenant via one edge → path gate withholds the *whole* path, not just the edge (§5), matching the existing sensitivity semantics.
- **T-unattributable-edge:** edge with `chunk_id = null` → already unreadable (fail-closed); workspace gate inherits this.
- **T-forgotten-predicate:** the residual Neo4j fragility → mitigated structurally by entity partitioning (§2) so even a missed WHERE cannot merge tenants, plus required-parameter threading (§6) so a missed scope fails loudly.

## 11. Out of scope (later product bricks)

Auth/session→workspace resolution (Kinde), workspace provisioning UI, and per-workspace Neo4j databases (an Enterprise-edition option we explicitly are *not* taking for V1 — query-level scoping + entity partitioning is sufficient and runs on Community).
