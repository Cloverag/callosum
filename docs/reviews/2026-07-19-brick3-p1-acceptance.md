# Brick 3 acceptance — Neo4j isolation → P1 multi-tenancy COMPLETE

**Status:** ✅ COMPLETE · **Date:** 2026-07-19 · **Owner:** Raghav
**Design:** `docs/proposals/2026-07-19-brick3-neo4j-isolation-design.md`

## What shipped (Brick 3)

| Sub-brick | Commit | Summary |
|---|---|---|
| 3.1 | `89faf6d` | Neo4j write-side stamping + **entity identity = (name, type, workspace_id)** — the structural partition; new constraints + indexes |
| 3.2 | `c13d293` | Neo4j read-side scoping — `Principal.workspace_id`, seed gate + extended `readable_edges` path gate, `entity_names_for_chunks` predicate |
| 3.3 | `bd9081f` | adversarial break-in tests (colliding entity names across two tenants) |

Integration suite: **8 passed** (RBAC candidate + 3 Postgres RLS isolation + 4 Neo4j break-in).

## Frozen-eval gate (Brick 3), vs `eval-baseline-v3`

Two runs through the full tenancy stack (RLS on, `callosum_app`, single Default Workspace):

| Metric | Run 12:57 (post-3.1) | Run 14:36 (post-3.2/3.3) | Baseline | Verdict |
|---|---|---|---|---|
| **Candidate recall** (REQUIRED) | 21/21 | **21/21** | 21/21 | ✅ PASS |
| **Traversal-given-grounding** (REQUIRED) | 100% | **100%** | 100% | ✅ PASS |
| Grounding recall (observed) | 17/21 | 17/21 | 17/21 | identical aggregate |

### Honest note — grounding distribution shifts run-to-run (LLM noise)
On run 14:36 the two grounding misses landed on M1/M2 (multi_hop): both had `candidate_hit=1`
(retrieval delivered the correct candidates) but `grounded_correct=0` (the LLM planner
mis-linked), **no error logged**. Aggregate grounding recall stayed 17/21; only *which*
questions missed changed — cloud-LLM (`gpt-oss:120b-cloud`) sampling nondeterminism, plus
a 429 on the conflict retry. This cascaded into the observed "multi_hop graph-fact recall
50%" and "ablation 95%" — all **downstream of the LLM**, none touching the REQUIRED metrics.
This is precisely the case for splitting a deterministic retrieval-only security eval from
the LLM grounding eval (see architecture-review issue #10, item 5).

## Decision

Neo4j workspace isolation is proven correct (break-in tests) **and** a byte-identical
single-tenant no-op on the required retrieval metrics. **Brick 3 accepted. P1 multi-tenancy
is COMPLETE** — both stores (Postgres RLS + Neo4j partitioning) enforce workspace isolation,
fail-closed, with the frozen research core's retrieval behaviour unchanged.

## Carried forward
- **PR #6 integration** (`entity_conflict` + `workspace_id`/RLS, re-parent migration) — now unblocked; tracked in #7.
- **Architecture review** (unbypassable tenancy, Postgres-canonical, split eval) — design-only, tracked in #10; starts after PR #9 (frontend) merges.
- Grounding **precision 50%** — pre-existing R13 open question, unrelated to tenancy.
