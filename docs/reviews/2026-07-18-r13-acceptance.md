# R13 — Research baseline acceptance and freeze

**Type:** Owner decision record (closes R13; unlocks P0)
**Date:** 2026-07-18
**Owner / reviewer:** Raghav
**Baseline commit:** `6ed5ed5` (`cp8-meeting14-identity` HEAD after adopting the gated planner)
**Supersedes as the live-accepted state:** `eval-baseline-v2` (`932f15a`, R7) — kept for history.

## Decision questions

| Question | Answer | Evidence |
|---|---|---|
| Have R8–R12 been evaluated live? | **Yes** | Clean full-denominator A/B run 2026-07-18 03:02 IST; both branches hit 21/21 candidate recall on the first try, no infra exclusions. `eval/ab_baseline_run1.md`, `eval/ab_salvage_run1.md`. |
| Are the metrics acceptable? | **Yes** | Candidate recall 100%, grounding recall 17/21 (81%), traversal-given-grounding 100%, K1 coreference fixed (✗→✓, traversal 0→100%), K2 sane abstention, zero regression on the other 20 graph questions. |
| Is the gated planner the final design? | **Yes** | Devguru's universal context injection measured a net grounding regression and is rejected; the gated `_needs_coreference_context` approach keeps the K1 fix without the collateral loss. Adopted as the CP8 planner (fast-forward into `cp8-meeting14-identity`). |
| Is the retrieval algorithm frozen? | **Yes** | Re-frozen at `6ed5ed5`. Any further core change requires a measured, reproducible benchmark gap per the exception process in `docs/research-handoff.md` / `CONTRIBUTING.md`. |

## Decision

**Research baseline ACCEPTED and FROZEN.** The verified-memory engine (ingest → verify →
quarantine → approve → store → retrieve → answer), the gated planner, the ontology, and the
stratified evaluation are the stable Callosum research contract. Product work (Track B, P0→P12)
builds on this without altering the frozen core.

## Threats to validity (scope of the claim)

The supported claim is that the gated planner **outperformed both the baseline and Devguru's
universal-context version on this evaluation run while avoiding the previously observed
regressions.** The +1 grounding-recall delta (16/21 → 17/21) comes from a single run and turns
on one question (K1); the *qualitative* result — gating avoids the universal regressions while
preserving the structural K1 fix (candidate pool 1 → 25) — is the strong claim, not the
magnitude. Grounding **precision (50%)** remains a documented open question (see Future
Research in `ROADMAP.md`); accepting the baseline freezes it as the reference, it does not
declare precision solved.

## Consequences

1. Tag the accepted state as the new immutable research baseline (see ROADMAP "R13").
2. `ROADMAP.md` R13 marked complete; **P0 is now authorized.**
3. PR #4 (`docs/r13-research-handoff`) is **not** part of this closure — its universal
   `retrieve.py` is superseded and it is 7 commits behind master. Its ALIAS_OF conflict
   workflow (`conflicts.py`) may be cherry-picked separately on its own merits; the PR itself
   should be closed or rebased, not merged.
