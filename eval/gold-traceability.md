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
