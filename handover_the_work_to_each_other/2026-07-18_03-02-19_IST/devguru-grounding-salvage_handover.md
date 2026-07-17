# Handover — Devguru grounding change: gated salvage confirmed, hand back for merge decision

## 1. Identity and scope

- **Repo:** callosum (local)
- **Timestamp:** 2026-07-18 03:02 IST
- **Topic:** A/B verdict on Devguru's frozen-core `retrieve.py` change. The *universal*
  context-injection version regressed grounding; a *gated* salvage recovers it and fixes K1.
  This note hands the gated approach back to Devguru with measured evidence.
- **Branches / last commits (both LOCAL ONLY, not pushed):**
  - BASELINE — `cp8-meeting14-identity` @ `bbc275d` (M14 + R12 instrumentation, no Devguru change)
  - SALVAGE  — `exp-devguru-grounding` @ `6ed5ed5` (gated context injection + reverted abstention)
- The **only runtime diff** between the two branches is `src/callosum/retrieve.py`
  (two test files also differ but do not execute during `callosum eval`, so the eval A/B is clean).

## 2. Status stated precisely

- **Implemented:** yes (gate `_needs_coreference_context`, 3 occurrences in retrieve.py on salvage branch).
- **Deterministically tested:** grounded/candidate/traversal columns compared across both runs.
- **Live evaluated:** yes — one clean full-denominator eval per branch (see §4).
- **Reviewed / formally accepted:** NO. This is still the frozen-core EXPERIMENT under
  evaluation, not a merge. CP8 (M14) merge decision is pending Devguru + owner.
- Roadmap gate: unchanged; do not update ROADMAP.md on the basis of this note alone.

## 3. What changed (salvage vs the universal Devguru version)

- Universal Devguru version: injected retrieval context on **every** question + tightened the
  abstention prompt. Measured net regression (grounding recall −5, no N1 fix).
- **Gated salvage:** context injection is gated to coreference-only via
  `_needs_coreference_context`, and the abstention prompt is reverted to baseline wording.
  Intent: get the K1 coreference fix without the collateral grounding loss on A1/C1/R1/T4.

## 4. Verification evidence

Environment: PROVIDER=ollama, chat `gpt-oss:120b-cloud` via local daemon → ollama.com,
embeddings local `bge-m3`. Gold graph SEEDED (deterministic): Neo4j 56 nodes / 81 rels,
BM12–16; Postgres 16 docs / 18 chunks all embedded. Containers not restarted, so no
reset/re-ingest was needed — `callosum eval` was run directly against the seeded graph.

Commands (each run to a per-run file):
```
git checkout cp8-meeting14-identity && .venv/bin/callosum eval --out eval/ab_baseline_run1.md
git checkout exp-devguru-grounding && .venv/bin/callosum eval --out eval/ab_salvage_run1.md
```

Both runs hit a **full 21/21 candidate-recall denominator on the first try** — no infra
exclusions, no reruns required.

| Deterministic mechanism metric | BASELINE `bbc275d` | SALVAGE `6ed5ed5` |
|---|---|---|
| Candidate recall (denominator) | 100% (21/21) | 100% (21/21) |
| **Grounding recall (correct seed)** | 76% (16/21) | **81% (17/21)** |
| Traversal (given grounding) | 100% | 100% |
| Grounding precision — abstention neg (N1/N2) | 50% (1/2) | 50% (1/2) |

Per-question, the deterministic `grounded` column is **identical on all 20 other graph
questions**; the only movement is:

- **K1** ("that proposal", coreference): `✗ → "Board Meeting 16"` (traversal 0%, 1 candidate)
  becomes `✓ → "Pricing rollout plan"` (traversal 100%, 25 candidates). **Fixed.**
- **K2** ("the prior motion", coreference NEGATIVE / M16 capability): stays `—` (abstains)
  in both, despite the gate injecting context (candidate pool 1 → 44). **Sane — no false ground.**
- **N1** (grounding_neg): `—` in both. Neg-precision unchanged at 1/2. Gate neither fixes nor
  regresses N1, as expected once the abstention prompt is reverted.

Not compared: single-run vector/hybrid **answer-text** columns — gpt-oss ignores temp=0 and
these flicker (e.g. A1/A3 hybrid flip between runs). Verdict rests only on the deterministic
mechanism metrics per the eval protocol.

Evidence files (this session): `eval/ab_baseline_run1.md`, `eval/ab_salvage_run1.md`
(also copied to session scratchpad `ab/`).

## 5. Verdict

The gated salvage is the approach to keep. Versus the universal version's measured −5
grounding regression, the gate:
- recovers **and exceeds** baseline grounding recall (17/21 vs 16/21, +1),
- **fixes K1** coreference grounding + traversal,
- keeps **K2 sane** (correctly abstains),
- causes **zero regression** on any other graph question,
- leaves **N1 precision unchanged**.

The K1 fix is structural, not variance: baseline cannot ground K1 (single candidate
"Board Meeting 16"); the gate surfaces the real referent among 25 candidates.

### 5.1 Threats to validity

The claim here is deliberately scoped. The gated approach **outperformed both the baseline
and the universal-context version on this evaluation run while avoiding the previously
observed regressions** — that is the supported statement, not "the gate is confirmed clean."

- The **+1 grounding-recall improvement (16/21 → 17/21) comes from a single evaluation run.**
  Grounding is an LLM step and the 16-vs-17 margin turns on a single question (K1). The
  magnitude of the improvement should be interpreted accordingly — it is *not* established as
  a stable aggregate delta.
- The **qualitative conclusion is the strong claim**: gating avoids the universal-context
  regressions (A1/C1/R1/T4 recovered) while preserving the K1 coreference fix, and the K1
  fix is structural (candidate pool 1 → 25) rather than a coin-flip. This holds independent
  of the exact ±1 on the aggregate.
- Not measured across repeated runs: answer-text columns (gpt-oss ignores temp=0 and these
  flicker) and the aggregate grounding recall itself. A confirmation run each side (§6) would
  bound the ±1; it is optional because the adoption case rests on the qualitative result, not
  the magnitude.

## 6. Outstanding work / recommended next action

- **OWNER DECISION MADE (2026-07-18):** keep the idea, discard the universal implementation.
  The gated `exp-devguru-grounding` planner is **adopted as the CP8 planner** — fast-forward
  merged into `cp8-meeting14-identity` (clean, no conflicts; brings `retrieve.py` + the two
  companion test files). Devguru's universal-context version (PR #4 / `docs/r13-research-handoff`,
  commit 8099d53) is **not** adopted for retrieval — it measured a net grounding regression.
  Devguru's insight (inject retrieval context for coreference) is what the gate preserves.
- **Still open (not this change):** PR #4 also carries the ALIAS_OF human-in-loop conflict
  workflow (`conflicts.py`, commit d9004bf), which was NOT part of this A/B and can be merged
  separately on its own merits. PR #4 as a whole is 7 behind master and conflicts on
  `retrieve.py`/`findings.md`/`ROADMAP.md`; whoever drives it should rebase and drop the
  superseded retrieval edit.
- **Not on master yet:** this adoption is on the CP8 line only. Do not merge CP8 to master
  until CP8 (M14) is formally accepted.
- Optional rigor before merge: one confirmation eval per branch to bound the ±1 on grounding
  recall (grounding is an LLM step; K1 fix is robust but the 16-vs-17 margin is a single Q).
  Costs ~2 cloud runs — weigh against Ollama session-usage limits.
- If accepted, port the two companion test updates
  (`tests/test_candidate_rbac_integration.py`, `tests/test_pipeline.py`) with the merge.

## 7. Guardrails

- Retrieval CORE remains FROZEN. This salvage is an experiment under evaluation, NOT yet merged.
- No ontology relations were added. Only benchmark-data / harness-side files touched otherwise.
- Both branches are LOCAL ONLY (no upstream). Nothing pushed. Whoever merges must decide the remote.
- Uncommitted at handover time: a `git stash@{0}` (WIP on cp8-meeting14-identity — regenerated
  eval output only, no source) exists from a branch-switch; safe to drop.
- Ollama account byjusynr222 previously hit an HTTP 429 session-usage limit after ~7 heavy runs.
  Quota was confirmed back this session (HTTP 200 probe). Do not create throwaway accounts to
  dodge limits; pace eval runs.
