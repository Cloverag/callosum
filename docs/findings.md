# Extraction findings log

Real observations from running the pipeline. Each entry: date, model, prompt/ontology
version, what happened, and what (if anything) we changed. This file feeds the
evaluation chapter.

## 2026-07-15 — gpt-oss:120b-cloud, prompt v1, ontology v1

**Cloud models ignore Ollama's `format` grammar.** Ollama compiles JSON-schema to a
constraining grammar for local models only. gpt-oss via cloud returned markdown
tables on full-size chunks (~3.2k chars) despite `format` being set — while passing
identical smaller inputs. Fix: schema embedded in the prompt as an explicit
instruction + one repair round-trip (model converts its own prose to JSON) +
balanced-object scan on parse. Transport-level constraint cannot be assumed off-host.

**A permissive parser can hallucinate an empty success.** Pydantic ignores unknown
keys and every Extraction field has a default, so a stray inner dict like
{"type": "Person"} validated as an EMPTY Extraction — one document ingested "cleanly"
with 0 proposals and no error. Guard added: a candidate must share ≥1 key with the
target schema. Silent-empty is the worst failure class; it looked like success.

**Glyph mismatch masqueraded as mass fabrication.** First full-chunk run: 13 kept /
17 quarantined (57% quote failure). After adding glyph equivalence classes
(typographic vs ASCII apostrophes/quotes/dashes) to locate(): 29 kept / 1 quarantined.
The model's quotes were faithful; the verifier was byte-picky. Lesson for the eval:
verify the verifier before reporting a fabrication rate.

**Residual true positive: ellipsis elision.** The model quoted
"We're not doing Model B. ... That's my call." — both halves real, but stitched with
an ellipsis, so not a contiguous verbatim span. Correctly quarantined under our
contract. Open question for prompt v2: forbid elision in quotes, or teach the
verifier to split on ellipses and require every part to locate. Frequency unknown —
watch the quarantine table after larger ingests.

**Polarity held on the real chunk.** Marcus OPPOSED the rejection, Priya SUPPORTED
it, Raj APPROVED it — correct on the interleaved 3-topic transcript, not just the
4-line regression snippet. The predicted worst failure mode has not materialized on
gpt-oss:120b. Keep the regression tests anyway; one clean run is not a distribution.
