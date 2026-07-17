# R12 instrumentation review — 2026-07-17

Records the R12 candidate-stage instrumentation run and the benchmark/infrastructure fixes
it motivated. **Decision fields are intentionally left open for the reviewer** — this record
accepts no checkpoint and authorizes no P0. It documents evidence and the freeze recommendation.

## Run identity

- Review date: 2026-07-17
- Reviewer(s): _pending_
- Branch / commit: `r12-abstention-hardening` @ `d149d36` (branched from `master` @ `868795b`)
- Comparison baselines: `eval-baseline-v2` (`932f15a`); R8-R13 live run (2026-07-16)
- Provider, chat, embedding: ollama · gpt-oss:120b-cloud · bge-m3
- Prompt / ontology: candidate-grounding planner / ontology v3 (`ALIAS_OF`)
- Corpus: 16 documents, 29 gold questions, 11 strata (unchanged from R8-R13)
- Commands: `.venv/bin/callosum eval` against the already-seeded gold graph
- Frozen core touched: **no** — grounding, verifier, quarantine, traversal, RBAC, approval
  are unchanged. `retrieve.ground()` is additive (zero behaviour change to `ask()`).

## Preconditions

- [x] Fast deterministic suite passed: **46 passed, 1 skipped, 5 deselected** (was 36).
- [x] `eval/results.csv` (runs 7-13) left byte-for-byte intact; this run appended to a new
      schema-versioned `eval/results-v2.csv` and the CLI announced the redirect.
- [x] No change to any frozen-core module's behaviour.
- [x] Embedding-NaN events were classified as infrastructure and excluded from grounding,
      not scored as linker failures.

## What was built (measurement, not algorithm)

- `retrieve.Grounding` + `ground()`: returns the plan, the candidate list handed to the
  planner, and per-stage timings. `grounded_plan()` delegates. No behaviour change to
  `ask()`/`vector_search`, so no frozen-core exception is required.
- Per-question eval fields: `candidates`, `candidate_hit`, `candidate_ms`, `plan_ms`.
- New metrics: `candidate_recall` (a hard ceiling on grounding), `linker_acc`,
  `loss_to_candidates` vs `loss_to_linker`, distractor load, stage latency. Report gains a
  "where grounding loss comes from" table.
- Infrastructure resilience (explicitly not part of the retrieval algorithm): `embed()`
  `keep_alive` + retry backoff; a bounded harness retry for the empty-candidate signature;
  `unretrieved` (infra) separated from `evaluated` in `grounding_traversal`.
- Benchmark corrections in `eval/gold.jsonl` (C2 consistency; M1/M2/A1/A2/A4 pricing
  disambiguation) with rationale in `eval/gold-traceability.md`.

## Results summary

Metrics are over the **retrieved** subset (unretrieved infra failures excluded and reported
separately). Latest run 2026-07-17; comparison to the R8-R13 live run (2026-07-16).

| Metric | R8-R13 (2026-07-16) | R12 run (2026-07-17) | Note |
|---|---:|---:|---|
| Graph questions | 21 | 21 | — |
| Unretrieved (embedding NaN) | 2–3 (not isolated) | 1 (T4) | now excluded, not mis-scored |
| Candidate recall (retrieved) | not measured | **100%** | R12's central result |
| Linker accuracy (retrieved seed) | — | 75% | see caveat below |
| Loss to candidate stage | — | **0%** | nothing to fix upstream of the linker |
| Traversal (given grounding) | 100% | **100%** | engine never the failure |
| Grounding precision — abstention negatives | 33% (1/3, pooled) | **50% (1/2)** | coreference negative removed from the pool |
| Ablation — grounding on | 83% | **95%** | benchmark corrections |
| Ablation — exact-match only | 48% | 45% | unchanged in character |
| Latency — candidate stage | not measured | **~245 ms** | embed + 2 store queries |
| Latency — planner | not measured | **~5000 ms** | ~20:1 vs candidate stage |

## Checkpoint evidence and decisions

### Candidate stage (R12 core)
- Candidate recall is 100% on retrieved questions; `loss_to_candidates` = 0%. The grounding
  loss is entirely linker selection, not candidate retrieval. Candidate/latency now isolated
  (the numbers the R8-R13 handoff said R12 acceptance required).
- Caveat: holds on the evaluated subset; revalidate on any corpus or embedding-path change.
- Decision: **Pass / Fail / Inconclusive — _reviewer_**

### Linker accuracy and the seed-vs-answer decoupling
- 75% seed accuracy understates answer quality. M1/M2/A2/A4 ground to the reversal
  (`Adopt Usage-Based Pricing`) yet answer correctly (recall 1.00) because `SUPERSEDES` +
  shared `ABOUT` let traversal bridge the two decisions; A1 grounds to the correct seed but
  answers wrong. On a densely-linked graph, seed-grounding accuracy does not track answer
  correctness — the metric over-reports failure.
- Decision: **accept the decoupling as a documented limitation of the seed metric — _reviewer_**

### Precision / abstention
- One genuine, repeatable abstention fault remains: N1 ("dynamic pricing engine" →
  Pricing Model B). The coreference negative (K2) is a missing M16 stage and is reported
  outside linker precision. One example is not a basis for an abstention algorithm.
- Decision: **defer abstention — _reviewer confirms_**

### Infrastructure (embedding NaN)
- Reduced (3→2→1 unretrieved across runs) but not eliminated; intermittent only inside the
  eval's local-embed/cloud-planner interleaving. The metric is robust either way (excluded,
  not mis-scored). Closing it fully is an open infra task, tracked separately from grounding.
- Decision: **accept as contained; NaN closure tracked as infra — _reviewer_**

### Benchmark corrections
- C2/C1 inconsistency fixed; pricing questions disambiguated by rewriting (not by weakening
  the linker); temporal questions still accept all three nodes by design. Rationale recorded.
- Decision: **Pass / Fail — _reviewer_**

## Reviewer decision (overall) and recommendation

- R12 acceptance: **_pending reviewer_**.
- **Recommendation: FREEZE.** Candidate recall full, traversal full, precision fault is a
  single case, and the headline grounding deficit was partly benchmark design and a
  partly-fixed infra bug. Do not design a new grounding algorithm until a clean rerun (NaN
  fully closed, corrected benchmark) still exposes a clear, repeatable bottleneck. The
  session's contribution is that instrumentation improved the benchmark and the measurement
  before any algorithm was written.
- Open follow-ups, in order: (1) close the bge-m3 NaN so a run is fully clean; (2) rerun and
  confirm the numbers hold; (3) reassess whether any grounding work is still justified;
  (4) coreference (M16) remains a distinct, unbuilt capability; (5) conflict synthesis (M15)
  remains a presentation gap, not a retrieval one.
