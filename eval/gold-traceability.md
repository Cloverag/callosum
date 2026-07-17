# Gold-question source traceability

Every record in `gold.jsonl` has a required `source_documents` array. Names are file stems
under `data/demo/`; the array identifies the corpus documents a reviewer must inspect before
changing the expected answer, forbidden answer, or graph facts. A negative grounding case
lists its deliberately nearby distractor document so the no-referent judgement is auditable.

The evaluator renders these source stems in its per-question Markdown table. Gold graph edges
remain document-aware: `GOLD_GROUPS` attaches every seeded relation to the source chunk from
which its verification quote was taken. The traceability tests reject an empty source list or
a source without a matching fixture.

The `messy_email` stratum adds two operational email records. They are intentionally clear
that a follow-up is not a board resolution or an approved target, exercising provenance and
restraint in realistic threaded-email language.

## Benchmark revision — 2026-07-17 (instrumentation-driven)

The R12 candidate-stage instrumentation surfaced two benchmark defects, corrected here.
These are evaluation fixes, not algorithm changes; the grounding/linker code was untouched.

- **C2 consistency.** C1 accepts the source-specific forecast nodes (`Finance FY27 ARR
  forecast`, `Sales FY27 ARR forecast`) as valid grounding for the FY27 conflict, but C2
  accepted only the abstract `FY27 ARR forecast`. Two questions about the same concept
  disagreed on the acceptable seed, so the linker was marked wrong on C2 for grounding to
  exactly the nodes C1 rewards. C2 now accepts all three, matching C1.
- **Pricing ambiguity (M1, M2, A1, A2, A4).** After M13 added the reversal, the corpus
  holds two decision nodes about the same topic — `Reject Pricing Model B` (original) and
  `Adopt Usage-Based Pricing` (its later supersede) — both `ABOUT Pricing Model B`. A bare
  paraphrase like "usage-based pricing" or "pay-per-use proposal" no longer identifies one
  node, so grounding to the reversal was scored as a linker error when it was a genuine
  referent. Rather than weaken the linker to force the older node, the questions were
  rewritten to name the intended decision explicitly ("the board rejected", "in the
  original board vote", "the proposal the board turned down"). They stay adversarial — the
  disambiguator adds no `Pricing Model B` tokens, so the lexical-distance challenge of the
  `grounding_adv` stratum is preserved. A4 previously read "the **new** commercial pricing
  plan", whose "new" pointed at the adopted model while gold expected the rejection; that
  wording is removed. Temporal questions (T1–T4) deliberately still accept all three nodes,
  because a question about the transition legitimately spans both decisions.

The lesson is recorded in `docs/findings.md`: instrumentation improved the benchmark itself
before any new grounding algorithm was justified.
