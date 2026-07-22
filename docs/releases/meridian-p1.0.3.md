# Meridian P1.0.3 — Release Notes (acceptance infrastructure)

**Tag:** `meridian-p1.0.3` (annotated) · **Anchored at:** master merge of `feat/eval-mechanism-gate`
**Date:** 2026-07-20 · **Type:** additive acceptance-gate infrastructure on `meridian-p1` · **Version:** `0.1.3`
**Research baseline:** `eval-baseline-v3` (unchanged) · **Implements:** Issue #10 idea 🥉 (split deterministic eval from LLM eval)

> A new **deterministic acceptance gate** with **no user-visible change** and **no change to the
> frozen core or the evaluation baseline**. It separates the reproducible mechanism metrics from
> the LLM-noisy answer metrics so releases stop being validated by hand-diffing noisy CSV columns.

## Why this release exists

Every recent release, the deterministic mechanism columns of `results-v2.csv` had to be **read by
hand** to separate a real regression from `gpt-oss` answer-text noise (the model ignores
`temperature=0`). This release makes that separation structural: a dedicated
`callosum eval-mechanism` gate computes only the deterministic tier and **exits non-zero** on any
regression. Design: `docs/proposals/2026-07-20-eval-mechanism-split.md`.

## The three tiers

```
Mechanism gate (REQUIRED, deterministic, no cloud LLM)   ← this release
    candidate retrieval · gold-seeded graph traversal · RBAC
Planner evaluation (OBSERVED, LLM-noisy)                 ← unchanged, in callosum eval
    grounding recall · GER · precision
LLM evaluation (OBSERVED, LLM-noisy)                     ← unchanged, in callosum eval
    answer-text / hybrid correctness
```

Traversal sits in the **required** tier because the traversal *engine* is deterministic given
seeds; only the planner's *choice* of seed is not. The gate therefore seeds traversal on the
**gold entities** (`GoldItem.expect_entities`), never the planner.

## What changed (all additive, non-frozen)

- **New `callosum eval-mechanism` subcommand** + `scripts/eval_mechanism.sh` — runs the tenant
  stack (RLS as `callosum_app`) with **zero cloud-LLM calls**. Writes `eval/mechanism.csv`
  (rows identical every run) and exits non-zero if any invariant regresses.
- **`evaluate.evaluate_mechanism()`** composes the frozen retrieval stages that make no
  planner/synthesis call (`candidate_entities`, `graph_search`, `vector_search`). The RBAC check
  is scoped to the `rbac` clearance stratum and verifies fail-closed on **both** retrieval
  surfaces (vector hits and traversed facts — the historical leak was through graph edge quotes).
- **6 DB-free gate-logic unit tests** (`tests/test_mechanism_gate.py`), incl. the RBAC-scope regression.

## New deterministic acceptance gate

Run on the tenant stack, **no cloud LLM required**:

| Check | Result | Required |
|---|---|---|
| candidate recall | **22/22** | = total |
| traversal recall (gold seeds) | **21/21 full (100% mean)** | = 100% |
| RBAC fail-closed | **1/1** (X1) | = total |

## What did NOT change (read these three carefully)

- **The candidate denominator moved 21 → 22 because the gate measures *all* gold-entity
  questions, NOT because recall changed.** The planner-eval's `candidate_recall` counted over
  "graph questions" (21); the mechanism gate counts every question that declares an acceptable
  gold entity (22). Both are 100%. This is a denominator definition, not drift.
- **`callosum eval` and the whole LLM evaluation path are unchanged** — byte-for-byte. This
  release only *adds* functions and a subcommand; `evaluate()`, `retrieve.py`, `store.py`,
  `eval.sh`, and `eval_tenant.sh` are untouched. `eval-baseline-v3` reproduction is therefore
  unaffected by construction, so it was not re-run.
- **No frozen file touched**; the D-001 ban-test stays green; fast suite 78 passed.

## Note from the first run (the gate earned its keep)

The gate **failed loudly on its first live run** — RBAC 1/8 — and pointed straight at a defect in
the harness itself: `rbac_applicable` was scoped to `bool(forbid_answer)`, which also matched the
7 non-clearance semantic-answer guards (temporal/conflict/coreference/messy_email) run as a
founder, whose forbidden text legitimately lives in readable chunks. Scoping the check to the
`rbac` stratum fixed it; the real clearance case (X1, investor cannot see the salary) passed
throughout. A deterministic gate that fails loudly and localises the defect is exactly the point
of the tier split — the same defect averaged into an LLM-noisy answer score would have been invisible.

## Status

Re-frozen at `meridian-p1.0.3`. Release line: `meridian-p1` → `p1.0.1` (F2 fix) → `p1.0.2`
(gateway / D-001) → `p1.0.3` (deterministic mechanism gate). Next: P2 continues one measured step
at a time — the `entity_conflict` UNIQUE-key migration is the queued owner-track item.
