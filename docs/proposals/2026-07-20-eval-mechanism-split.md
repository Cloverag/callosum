# Design — Split the deterministic mechanism eval from the LLM eval

**Status:** Accepted (owner, 2026-07-20) · **Area:** evaluation harness (non-frozen) ·
**Motivates:** Issue #10 idea 🥉 ("split deterministic-retrieval eval from LLM eval") ·
**Frozen core:** untouched — no `retrieve.py`/`store.py` change, no eval-baseline-v3 exception.

## Problem

`callosum eval` runs one loop that produces, per question, both **deterministic mechanism
metrics** (candidate recall, traversal) and **LLM-dependent metrics** (grounding recall/GER/
precision, answer-text correctness) — and writes them to one CSV. The LLM columns flicker
run-to-run because `gpt-oss:120b-cloud` ignores `temperature=0`; every recent release we have
had to **hand-diff the deterministic columns of `results-v2.csv`** to prove a change was model
noise and not a regression. That manual step is the recurring cost this design removes.

The conceptual split already exists — `eval_tenant.sh`'s acceptance block distinguishes
REQUIRED (candidate recall 21/21, traversal 100%) from OBSERVED (grounding, 429s). This makes
that line **structural and enforceable**, not a comment.

## The three tiers

```
Mechanism gate (REQUIRED, deterministic, no cloud LLM)
    candidate retrieval   — vector_search + entity_names_for_chunks (local bge-m3)
    graph traversal       — graph_search seeded on the GOLD entities
    RBAC                   — fail-closed on both retrieval surfaces
        ↓  gates the release
Planner evaluation (OBSERVED, LLM-noisy)
    grounding recall · GER · precision      — the planner CHOOSES the seed
        ↓  recorded, never gated
LLM evaluation (OBSERVED, LLM-noisy)
    answer-text / hybrid correctness         — synthesised prose, substring-scored
```

This mirrors how release decisions have actually been made across `meridian-p1` → `p1.0.2`:
deterministic mechanism columns decide; answer-text is recorded and discounted as noise.

## Why traversal is in the deterministic gate (the key call)

The traversal **engine** is deterministic — given a set of seed entities, 2-hop `graph_search`
returns the same facts every time. Only the planner's **choice** of seed is nondeterministic.
So the gate tests traversal by supplying the **gold seeds** (`GoldItem.expect_entities`)
directly to `graph_search`, never the planner. Graph-engine correctness stays in the required
gate; seed selection stays in the observed tier where it belongs.

Note this makes the gate's traversal number **different from — and cleaner than — the old
"ablation" column.** Today's ablation seeds traversal via `plan(question)` with no vocabulary,
which still calls the cloud planner (~38% recall). Gold-seeded traversal targets **100%**: with
correct seeds the engine must recall every expected fact. Acceptance is therefore "== 100%",
not "match the old ablation column".

## What gets built (all non-frozen)

- `evaluate.evaluate_mechanism(conn, driver, gold) -> MechanismReport` — computes only the
  three deterministic metrics by **calling** the frozen stages (`candidate_entities`,
  `graph_search`, `vector_search`). Zero planner/synthesis calls.
- `evaluate.write_mechanism_csv(report, path)` → `eval/mechanism.csv`. Unlike `results.csv`
  these rows are **identical every run** — a diff here is a real regression, not model noise.
- `callosum eval-mechanism` — a **separate subcommand** (own CI target; cannot invoke the LLM
  path), exits non-zero if any check regresses.
- `scripts/eval_mechanism.sh` — reset → migrate (tenancy) → ingest `--no-extract` → `seed-eval`
  → `eval-mechanism`. Same corpus/seed as `eval_tenant.sh`, but no cloud LLM.
- Unit test on `MechanismReport` aggregation + `passed` (no DB needed).

`callosum eval` / `eval.sh` / `eval_tenant.sh` are **unchanged** — the LLM eval keeps working
exactly as now.

## The gate (`MechanismReport.passed`)

Every applicable check must be perfect **and** each tier must actually have run (an empty tier
is a broken harness, not a pass):

- candidate recall `== total` (baseline **21/21**)
- gold-seeded traversal recall `== 100%` on every `expect_facts` item
- RBAC fail-closed on every `forbid_answer` item (both vector hits and traversed facts — the
  historical leak was through **graph edge quotes**, so both surfaces are checked)

## Acceptance for THIS change

- `scripts/eval_mechanism.sh` passes the gate on a clean tenant DB (candidate 21/21, traversal
  100%, RBAC all pass) — reproducing the deterministic half of `eval-baseline-v3`.
- Fast suite green (new unit test included).
- `callosum eval` deterministic numbers unchanged (the LLM path is not touched).
- No frozen file modified.

## Non-goals / deferred

- **Fully-offline determinism** (pre-cached query embeddings). The gate still needs local
  bge-m3 + Postgres + Neo4j. Invariant is "no *cloud* LLM," not "no dependencies." Caching is a
  future optimization, not this pass.
- CI wiring itself (GitHub Actions) — the subcommand is the CI target; hooking it up is separate.
