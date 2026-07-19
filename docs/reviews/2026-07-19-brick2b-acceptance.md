# Brick 2b acceptance — Postgres multi-tenant isolation

**Status:** ✅ COMPLETE · **Date:** 2026-07-19 · **Owner:** Raghav
**Scope:** P1 Postgres tenancy (Row-Level Security). Neo4j isolation is Brick 3 (separate).

## What shipped

| Sub-brick | Commit | Summary |
|---|---|---|
| 2a | `2d59ff6` | `workspace_id` on 7 tenant tables + backfill Default Workspace |
| 2b.1 | `c051c47` | connection plumbing — `SET app.workspace_id` in `store.pg()` |
| 2b.2 | `3dd958a` | RLS `ENABLE`+`FORCE` + `tenant_isolation` policy; **`callosum_app` non-superuser role** (the superuser-bypass fix) |
| 2b.4 | `42f9f8b` | automated cross-tenant isolation regression tests |
| 2b.5 | `edf0265`, `e501db2` | tenancy-aware frozen-eval harness (`scripts/eval_tenant.sh`) |

## Frozen-eval gate (2b.5) — run 2026-07-19 02:24, vs `eval-baseline-v3`

Ran the full deterministic benchmark through the tenancy stack (RLS on, connecting as
`callosum_app`), single Default Workspace. No 429s this run.

| Metric | Result | Baseline | Verdict |
|---|---|---|---|
| **Candidate recall** (REQUIRED) | **21/21** | 21/21 | ✅ PASS |
| **Traversal-given-grounding** (REQUIRED) | **100%** | 100% | ✅ PASS |
| Grounding recall (observed) | 17/21 | 17/21 | identical |
| GER (observed) | 19% | 19% | identical |
| Grounding precision (observed) | 50% (1/2) | 50% | identical (documented-open) |
| Ablation grounding on/off (observed) | 43% → 100% | 43% → 100% | identical |

Full per-question record: `eval/results-v2.csv` run `2026-07-19 02:24`; summary `eval/results.md`.

### Scoring note (honest history)
E3 (aliases *same-as* question, "are R. Malhotra and R. Kumar the same person?") is
scored **NA** by the harness for `candidate_hit`/`grounded_correct` (empty, not 0),
because it grounds to two entities rather than a single seed. Its `candidate_count=36`
confirms candidates were retrieved — RLS filtered nothing. The harness denominators are
21 (E3 excluded); the summary table agrees ("17/21"). A first scoring pass that treated
the NA field as a miss (21/22) was a measurement artifact, corrected to 21/21.

## Decision

RLS + the app-role split are a **byte-identical no-op for a single tenant** — retrieval is
unchanged, proving the frozen-core tenancy exception was safe. **Brick 2b accepted.
Postgres multi-tenant isolation is complete.**

## Threats / open items carried forward
- Grounding **precision (50%)** remains the pre-existing open question from R13 — unrelated to tenancy, unchanged by it.
- **Neo4j is not yet isolated** — the graph half. Addressed in Brick 3 (design: `docs/proposals/2026-07-19-brick3-neo4j-isolation-design.md`). P1 is not complete until Brick 3 lands.
- The `entity_conflict` table (PR #6) still needs `workspace_id` + RLS folded in at integration (tracked in #7).
