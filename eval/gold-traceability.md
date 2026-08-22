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

## Benchmark revision — 2026-08-23 (messy CRLF corpus)

Six records added against the two CRLF documents introduced in #146, taking the set from
30 to 36. Both documents are now ingested by `scripts/eval.sh` and
`scripts/eval_mechanism.sh`, so these questions have a corpus to answer from.

The corpus they test is deliberately degraded — CRLF line endings, three speaker labels
for one person, typos, OCR corruption, an unresolvable pronoun, and two note-takers
minuting different figures. Every record here exists because a *clean* corpus cannot
exercise the thing it tests.

| ID | Stratum | What it exercises |
|---|---|---|
| `L4` | lookup | Retrieval through OCR corruption — the email renders Northwind as "Norlhwind" twice, and the answer must still name the company |
| `C3` | conflict | Two figures for one number **inside a single document** (Marcus minutes 40,000, Tom has 14,000), corrected by a later email. Forbids the wrong figure rather than only expecting the right one |
| `T5` | temporal | A three-document supersede chain: M12 rejected Pricing Model B, M13 reversed that, M17 supersedes it with a tiered floor |
| `E5` | aliases | One person under `PRIYA:`, `P. Nair:` and `Priya N.:` in one transcript |
| `N3` | grounding_neg | An unresolvable reference the corpus itself refuses to resolve — Tom declines to name "the earlier motion" and Priya minutes it as ambiguous. Grounding to either candidate is the failure |
| `D3` | messy_email | Restraint: a correction email must not be read as changing a status it explicitly leaves alone |

**`expect_entities` and `expect_facts` are empty on all six.** They are answer-and-retrieval
cases, not graph-fact cases, because seeding them into `GOLD_GROUPS` would change the
seeded gold graph's entity and edge counts — figures quoted on the dashboard and in
`README.md`. Extending the gold graph to cover this chain is a separate change with its
own measurement, and should not ride along with a corpus addition.

**Expect the numbers to move.** Two more documents mean more chunks in vector search and
more candidate names for the linker; #92 predicts grounding recall in particular may fall.
A drop is the finding, not a failure, and nothing here should be tuned to prevent one.
