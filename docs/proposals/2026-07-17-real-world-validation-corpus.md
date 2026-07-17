# Proposal — real-world validation corpus

**Status: proposal only.** No documents are added and no eval changes are made by this file.
The purpose is to plan validation *beyond* the synthetic benchmark and justify each document
by the capability it stresses that our clean, hand-authored corpus cannot.

## Why we need this

Every document in `data/demo/` was written to isolate one capability, in clean prose, by us.
That is the right design for *unit-testing* retrieval — but it means the benchmark shares the
author, the vocabulary, and the tidiness of the system under test. Three risks follow:

1. **Optimistic extraction.** Verified extraction depends on finding a *contiguous, single-
   speaker* evidence span. Our transcripts are written to have clean spans. Real documents
   fracture quotes across turns, interruptions, and formatting — the verifier may quarantine
   far more, and we have never measured that rate on adversarial input.
2. **Optimistic grounding.** Our entities are spelled consistently. Real corpora spell the
   same entity five ways and two different entities almost identically (the exact stress the
   M14 draft introduces synthetically — this measures it on text we did not sanitise).
3. **Optimistic answers.** Clean sources make the synthesis job easy. Noise, hedging, and
   partial information are where a "verified" system should *refuse or hedge* — the behaviour
   that most distinguishes it from fluent RAG, and the behaviour our clean corpus never tests.

The goal is not a bigger benchmark. It is a **held-out stress set** that can only lower our
numbers — if it does not, that is strong evidence the capabilities generalise.

## Proposed documents (small, ~6 — each targets one real-world failure mode)

| # | Document | Real-world noise it introduces | Capability it stresses beyond the synthetic set |
|---|---|---|---|
| 1 | **Auto-generated meeting transcript** (Otter/Zoom-style, verbatim) | Speaker mislabels, "[inaudible]", filler, mid-sentence turn changes | Evidence-span verification: can a quote be located when the speaker attribution is wrong and the sentence is split across turns? Expect a higher, measurable quarantine rate. |
| 2 | **Scanned/OCR'd board memo (PDF)** | OCR substitutions (rn→m, 0→O, l→1), broken hyphenation, column bleed | Extraction robustness to character noise; whether entity names survive OCR well enough to ground. Directly tests the `.pdf` path on *non-native* text, unlike our clean generated PDF. |
| 3 | **Long email thread with quoted replies** | Repeated quoted text, top-posting, "see below", changing subject lines | Coreference and reference resolution across quoting depth ("that proposal", "the number you mentioned") — the M16 gap, on genuinely tangled threading rather than one clean reference. |
| 4 | **Two documents that disagree on a name** (org chart vs signed approval) | Inconsistent names/titles for one person; a stale title | Identity grounding + provenance under conflict, without us authoring the conflict — does `ALIAS_OF` stay evidence-backed when the evidence is itself messy? |
| 5 | **Chat/Slack export of an incident** | Typos, abbreviations, emoji, out-of-order timestamps, half-finished lines | Extraction from interrupted, ungrammatical dialogue; whether decisions ("we're rolling back") are recoverable when never stated in a clean sentence. |
| 6 | **Redacted / partially-missing document** | Blacked-out spans, "[REDACTED]", truncated pages | Graceful incompleteness: does the system abstain and say a source was withheld/partial, rather than hallucinate across the gap? Tests refusal on *content* absence, complementing RBAC's refusal on *permission*. |

## How to run it (when approved — not now)

- **Held-out, not merged.** Keep this set separate from `eval/gold.jsonl` so it never trains
  our intuition or gets optimised against. Run it as a one-off generalisation check.
- **Report the deltas that matter:** quarantine rate (doc 1, 2, 5), grounding recall/precision
  on noisy names (doc 2, 4), coreference recall (doc 3), and *abstention rate* on docs 5–6
  where the honest answer is often "not enough information."
- **Provenance, not licensing risk.** Prefer synthetic-but-messy documents we generate to
  *look* real (OCR-degraded, auto-transcribed) over real third-party documents, to avoid
  confidentiality and copyright issues. The noise is the point, not the specific content.

## The bar this sets

If the frozen core holds up on documents it did not author — quarantine stays sane, grounding
degrades gracefully, and abstention rises where information is genuinely missing — that is a
far stronger thesis claim than any number on the clean benchmark. If it does not, this set
tells us *exactly which* capability breaks first on real input, which is the next evidence-
backed reason to unfreeze.
