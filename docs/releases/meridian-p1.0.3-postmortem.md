# Postmortem — Meridian P1.0.3

**Release:** `meridian-p1.0.3` (`ebf2849`) · **Date:** 2026-07-20 · **Outcome:** shipped clean; one
harness defect caught by the gate on its first run and fixed before merge.

A postmortem is written for every release even when nothing failed. This one has a real teaching
moment: the new gate found a bug in *itself* on run one.

## 1. What surprised us?

- **The gate's first live run failed — and that was the good outcome.** RBAC came back 1/8, which
  looked alarming until the rows showed 7 of the 8 were non-clearance semantic-answer guards run
  as a founder. The deterministic gate localised a harness defect in seconds; the same wrong count
  averaged into an LLM-noisy answer score would have been invisible. The failure *was* the feature.
- **`forbid_answer` is overloaded.** It marks both a clearance secret (rbac stratum) and a
  "don't assert the superseded/wrong fact" answer guard (temporal/conflict/coreference/messy_email).
  Only the former is a retrieval-filter invariant. The `stratum` label is the real discriminator.

## 2. What was harder than expected?

- **Deciding what is truly deterministic was subtler than "LLM vs not."** It is three tiers, and
  traversal straddled the line: the engine is deterministic, the planner's *seed choice* is not.
  The resolution (seed traversal on gold entities) came from the reviewer, not the first design.

## 3. What almost went wrong?

- **Shipping the over-broad RBAC check.** Had the gate not been run live before merge — or had it
  been written to only warn instead of exit non-zero — the false "leak" logic would have merged and
  every future run would have mis-reported RBAC. Running the acceptance gate *before* the merge
  decision (not after) is what caught it.

## 4. What should become a rule?

- **A gate must fail loudly and localise — never average, never warn-only.** Non-zero exit + a
  per-item CSV is what turned a vague "RBAC 1/8" into a one-line root cause. Keep deterministic
  logs row-per-item and byte-identical across runs so a diff *is* the regression.
- **Run the new acceptance gate on real data before the merge decision, not after.** The mechanism
  gate found its own defect only because it ran live pre-merge. (Reinforces the p1.0.2 rule that a
  merge is an explicit decision gated on evidence.)
- **Scope security checks by intent, not by a proxy field.** `stratum == "rbac"`, not
  `bool(forbid_answer)`. A field reused across purposes is not a security signal.

## 5. What should we never do again?

- **Never infer a security condition from an overloaded field.** The false leaks came entirely from
  reading `forbid_answer` as an RBAC marker. When a check is security-critical, tie it to the
  explicit label that means exactly that condition.

---

*Design-first paid off: the split was designed (`docs/proposals/2026-07-20-eval-mechanism-split.md`),
reviewed (the gold-seed refinement), then built — and the one defect that slipped through the design
was caught by the artifact the design produced. §4 rules feed `docs/releases/README.md`.*
