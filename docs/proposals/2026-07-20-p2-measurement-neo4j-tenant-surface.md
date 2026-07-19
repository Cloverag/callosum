# P2 Track-A Measurement — Neo4j tenant-filter surface & misuse risk

**Date:** 2026-07-20 · **Author:** owner (Track A) · **Type:** measurement (read-only audit; no code changed)
**Purpose:** Before committing to a P2 RFC, measure *where* tenant isolation is actually enforced in the
Neo4j layer, how misuse-prone that surface is, and whether any real defect already exists — so the
evidence picks the RFC rather than the ranking. Baseline audited: `meridian-p1` (`04dfd2f`).

---

## Method

Enumerated every Cypher execution site (`session.run(...)`) in `src/callosum/` and classified each by
whether it carries a `workspace_id` predicate. Neo4j has no RLS, so isolation there is enforced *only*
by the query text itself — every read/write must remember the predicate by hand.

## Inventory — every Cypher site

| # | Site | File:line | Kind | Workspace-scoped? |
|---|------|-----------|------|-------------------|
| 1 | `ensure_constraints` | store.py:342 | DDL | n/a (constraint includes `workspace_id`) |
| 2 | `entity_names` | store.py:353 | read | ❌ **no filter** — returns all tenants' entity names |
| 3 | `entity_names_for_chunks` | store.py:373 | read | ✅ `c.workspace_id` + `e.workspace_id` |
| 4 | `upsert_chunk_node` | store.py:397 | write | ✅ stamps `c.workspace_id` |
| 5 | `apply_entity` | store.py:422 | write | ✅ `workspace_id` in MERGE identity |
| 6 | `apply_relationship` | store.py:454 | write | ✅ MATCHes both entities by `workspace_id` |
| 7 | `graph_search` | retrieve.py:400 | read | ✅ `seed.workspace_id` + `src.workspace_id` |
| 8 | `_entity_mentions` | conflicts.py:56 | read | ❌ **no filter** — reads all tenants' entities |
| 9 | `_already_known` | conflicts.py:117 | read | ❌ **no filter** — matches identity on `(name,type)` only |

**5 of 8 query sites are correctly scoped; 3 are not.** The invariant is duplicated as hand-written
predicates across at least 5 sites (`c.workspace_id`, `e.workspace_id`, `seed.workspace_id`,
`src.workspace_id`, MERGE identity) — the exact "N locations, someone forgets one" surface.

## Findings

### F1 — Isolation is enforced by convention at N sites, not by construction.
Brick 3 scoped `store.py` + `retrieve.py` by hand. Correct, but the guarantee lives in the author
remembering the predicate at every new Cypher site. There is no structural barrier stopping a raw
`session.run(...)` from omitting it.

### F2 — LIVE GAP: the entity-conflict detector is workspace-blind. *(real, not latent)*
`conflicts.py` (Devguru's PR #6, merged into `meridian-p1`) has its **own** raw Cypher, outside the
files Brick 3 scoped, and it was never tenant-scoped:
- `detect_conflicts(conn, driver)` (conflicts.py:156) takes **no workspace/principal**.
- `_entity_mentions` reads **every workspace's** entities and pairs them (`_candidate_pairs`).
- `_already_known` checks ALIAS_OF on `(name,type)` only — ignores `workspace_id`.
- Approve path (`apply_relationship`) defaults to `DEFAULT_WORKSPACE_ID`, so a cross-tenant approval
  mis-resolves to the default workspace or silently no-ops.

**Blast radius (measured, honest):**
- *Contained:* the Postgres `entity_conflict` table has `workspace_id NOT NULL DEFAULT <default_ws>` +
  RLS `ENABLE`+`FORCE` with `USING` **and** `WITH CHECK` (migration 0005). The detector always runs via
  `store.pg()` = the *default* workspace session (cli.py:271), so rows can only land in that session's
  queue, and evidence quotes come through the RLS-scoped `chunk` read (`_chunk_quote`) → other tenants'
  **quotes are blocked**.
- *Leaked:* entity **names** come from Neo4j (no RLS), so in a multi-tenant deployment the default
  workspace's conflict queue is populated with **other tenants' entity names**, paired across tenants,
  and proposes cross-tenant ALIAS_OF edges. Names + graph structure cross the boundary; the feature is
  workspace-blind by construction.

This is not a remote "tenant A calls the API and reads tenant B" exploit (RLS + the default-session
flow contain that). It *is* a genuine isolation defect in merged P1 code and a concrete instance of F1.

### F3 — `store.entity_names` (site 2) is dead but loaded. *(latent footgun)*
No caller anywhere (`grep` confirms). But it's an unscoped cross-tenant read sitting in the public store
API; an earlier design wired it into the planner as grounding vocab. Re-wiring it would leak entity
names across tenants with no test to catch it.

### F4 — Zero test coverage on the conflicts path.
`tests/test_graph_tenant_isolation.py` proves entity-identity partitioning, `graph_search`,
`entity_names_for_chunks`, and wrong-workspace principals — but **nothing exercises `conflicts.py`**. The
gap in F2 is untested in either direction.

---

## What the evidence says about the RFC

The measurement **confirms 🥇 the Neo4j query gateway as P2 RFC #1 — now evidence-backed, not assumed.**
The failure in F2 is precisely the one a single governed gateway prevents: a whole feature's raw Cypher
skipped tenant filtering because isolation is a per-site convention, not a chokepoint. Ranking said
"gateway first"; the evidence says the same for a concrete reason.

Design intent (to be detailed in the RFC): one module is the *only* place allowed to open a Neo4j
session; it takes a `workspace_id`/`Principal` and injects the predicate centrally; a lint/test bans raw
`session.run(` outside it. Then N→1: adding a query cannot forget the filter.

## Recommended P2 sequencing

1. **Write the failing test first** — add a conflict-path case to `test_graph_tenant_isolation.py`
   proving two tenants' entities get cross-paired by `detect_conflicts`. Red test = reproduced defect.
2. **Implement the gateway RFC** as the fix vehicle: route `store.py`, `retrieve.py`, **and**
   `conflicts.py` Cypher through it; give `detect_conflicts` a `workspace_id`; delete or gate the dead
   `entity_names` (F3). The gateway *is* the fix for F2 — don't hand-patch conflicts.py separately.
3. **Freeze + verify vs `eval-baseline-v3`** (single-tenant retrieval must stay byte-identical:
   candidate recall 21/21, traversal 100%) and confirm the new red test goes green.

**Owner decision needed:** treat F2 as (a) a bug-fix against `meridian-p1` done now, or (b) folded into
the gateway RFC as recommended above. Recommendation: **(b)** — it keeps the frozen baseline stable and
makes the RFC's success measurable against a real reproduction rather than a hypothetical.

## Success metrics for the RFC (per Issue #10)

- Tenant-filter locations in Neo4j: **N → 1** (currently ≥5 hand-written predicate sites + 2 that forgot).
- A new raw `session.run(` outside the gateway **fails a test/lint**.
- `detect_conflicts` is per-workspace; the F2 red test passes.
- `eval-baseline-v3` deterministic metrics unchanged.
