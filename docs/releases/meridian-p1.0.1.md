# Meridian P1.0.1 — Release Notes (patch)

**Tag:** `meridian-p1.0.1` (annotated) · **Anchored at:** master merge of `fix/conflicts-tenant-scope`
**Date:** 2026-07-20 · **Type:** correctness patch on `meridian-p1` · **Version:** `0.1.1`
**Research baseline:** `eval-baseline-v3` (unchanged)

> A boring, invariant-restoring patch. No new abstraction, no frozen-core change — it makes the
> entity-conflict feature honor the tenant boundary the rest of P1 already enforces.

## Why this patch exists

The P1 measurement pass (`docs/proposals/2026-07-20-p2-measurement-neo4j-tenant-surface.md`, finding
**F2**) found that `conflicts.py` (merged via PR #6) ran its **own** raw Cypher outside the helpers
Brick 3 scoped, so `detect_conflicts` was **workspace-blind**: it paired entities across all tenants
and could surface other tenants' entity names into the default workspace's conflict queue, and
`approve_conflict` created the ALIAS_OF edge in the default workspace regardless of the tenant.

This is a **verified correctness defect against an existing invariant**, not a new feature: ROADMAP
P1's own exit criterion requires *"unauthorized content is blocked in SQL, **Cypher**, quotes, chunks,
logs, APIs, and UI."* Leaving it in the baseline would make `meridian-p1` stop reflecting its own
stated guarantee — hence a patch now rather than deferring to the P2 gateway.

## What changed (4 files, +57/−13)

- `conflicts.py`: `_entity_mentions` and `_already_known` now filter on `workspace_id`;
  `detect_conflicts(*, workspace_id=…)` threads it and stamps the `entity_conflict` row explicitly;
  `approve_conflict` carries the conflict's `workspace_id` into the ALIAS_OF payload so the edge lands
  in the right tenant.
- `cli.py`: both callers pass `DEFAULT_WORKSPACE_ID` explicitly (single-tenant behavior unchanged).
- `__init__.py`: `0.1.0 → 0.1.1`.
- `tests/test_graph_tenant_isolation.py`: new regression `test_conflict_scan_cannot_cross_workspace`.

No frozen-core file (`ingest/extract/retrieve/store/schema`) was touched — `conflicts.py` is
explicitly non-frozen.

## Verification

- **Integration: 9/9 pass on a clean DB**, including the new regression test. (An earlier local run
  showed 1 failure caused purely by leftover eval-corpus data in the DB; it passed on a fresh volume.)
- **Frozen retrieval unchanged vs `eval-baseline-v3`:** traversal 100%, ablation 38% → 100%, grounding
  17/21 (81%), GER 19%, precision 1/2, graph-fact recall 100% on all graph strata. The deterministic
  mechanism columns in `results-v2.csv` are byte-identical to the prior run; only nondeterministic
  answer-text scores flickered (documented gpt-oss behavior).

## Known follow-up (not in this patch — for the P2 gateway RFC)

The `entity_conflict` UNIQUE key is `(name_a, type_a, name_b, type_b)` **without** `workspace_id`, so
the same name pair across two tenants would collide on one row. Latent until multi-tenant detection
actually runs; fold into the Neo4j gateway RFC or a dedicated schema migration.

## Status

Re-frozen at `meridian-p1.0.1`. Next owner work: the Neo4j query gateway RFC (Defect Class **D-001**:
unscoped Neo4j access), with F2 as its concrete motivating precedent.
