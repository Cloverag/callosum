# Meridian P1.0.2 — Release Notes (patch)

**Tag:** `meridian-p1.0.2` (annotated) · **Anchored at:** master merge of `feat/neo4j-gateway`
**Date:** 2026-07-20 · **Type:** internal safety hardening on `meridian-p1` · **Version:** `0.1.2`
**Research baseline:** `eval-baseline-v3` (unchanged) · **Implements:** P2-RFC-001

> An internal safety refactor with **no user-visible change**. It makes the class of bug behind F2
> structurally impossible for future Neo4j access, without touching the frozen retrieval core.

## Why this patch exists

`meridian-p1.0.1` fixed the F2 *instance* (workspace-blind entity-conflict detection). This patch
closes the *class* — **D-001: unscoped Neo4j access** — per the accepted design in
`docs/proposals/2026-07-20-P2-RFC-001-neo4j-gateway.md`. Isolation in Neo4j had relied on every call
site remembering the `workspace_id` predicate; a whole feature already forgot once.

## What changed

- **New gateway `callosum/graph.py`** — a *bounded* repository (`GraphContext` + `GraphGateway`) with
  exactly the two methods the migration needs (`entity_mentions`, `alias_edge_exists`). No raw-Cypher
  entry point exists, and workspace scoping is injected centrally, so a caller cannot express an
  unscoped query. No generic `query()`, no ORM, no speculative methods.
- **`conflicts.py` migrated** onto the gateway — it now opens **zero** Neo4j sessions.
- **Dead `store.entity_names` removed** (F3) — an unscoped cross-tenant read with no callers.
- **CI ban-test `tests/test_no_raw_cypher.py`** — an AST-based security test: opening a Neo4j session
  (`.session()`) anywhere outside the gateway or the explicit frozen allowlist fails the build. D-001
  is now an enforced invariant, not a review guideline.

## Grandfathering (temporary)

The frozen, eval-verified query sites in `store.py`/`retrieve.py` are allowlisted at **(module,
function)** granularity — not because they are special, but because they already satisfy the invariant
and are covered by the frozen evaluation baseline. **The allowlist is temporary:** it is retired at the
next planned retrieval change, when those sites migrate into the gateway before further retrieval work.

## Verification

- **`eval-baseline-v3` deterministic metrics unchanged** (via `scripts/eval_tenant.sh`, through RLS as
  `callosum_app` on a fresh migrated DB): traversal 100%, ablation 38% → 100%, grounding 17/21, GER
  19%, precision 1/2, graph-fact recall 100%. Answer-text columns flicker (documented gpt-oss noise);
  every deterministic mechanism column matches baseline.
- **Integration 9/9** on a clean DB, including the F2 regression now exercising `gw.entity_mentions`.
- **Ban-test green** — `conflicts.py` opens no sessions; only the frozen allowlisted sites remain.
- No frozen retrieval file touched.

## Out of scope (unchanged from p1.0.1)

The `entity_conflict` UNIQUE key still omits `workspace_id` (cross-tenant row collision, latent until
multi-tenant detection). Tracked as a separate schema migration, not a gateway concern.

## Status

Re-frozen at `meridian-p1.0.2`. Release line: `meridian-p1` → `meridian-p1.0.1` (F2 fix) →
`meridian-p1.0.2` (gateway hardening). Next: the allowlist retirement rides the next retrieval change;
otherwise P2 continues one measured step at a time.
