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

## 2026-07-15 (run 2) — first full end-to-end ingest, gpt-oss:120b-cloud, prompt v1

**93 edges committed to the graph. Pipeline ran end to end** (ingest → verify →
quarantine → approve → Neo4j) for the first time. Two board documents, 57 + 36
proposed edges, 4 quarantined.

**The two golden edges were quarantined, and the reason is a genuine win.** Raj
APPROVED and Marcus OPPOSED the pricing rejection — the highest-value edges in the
demo — were refused with `quote_not_found`. Cause: the model stitched non-adjacent
sentences into one quote.

  - Raj: "We're not doing Model B. Rejection for this fiscal year." — two of Raj's
    turns, with Tom's interjection between them. Not contiguous.
  - Priya (on the hiring freeze): "The B closed... So the freeze comes off." —
    **stitched across two speakers**: Priya said "The B closed", Raj said "the
    freeze comes off". This attributes Raj's words to Priya. This is exactly the
    failure the system exists to prevent, and the verifier caught it.

Priya SUPPORTED and Elena SUPPORTED the rejection *did* land (single contiguous
quotes), so the decision is partially represented but missing its final-call and
opposition edges. Under our contract that is correct behaviour: a missing edge beats
a misattributed one. Fix is recall-side, not enforcement-side.

**Response: prompt v2** forbids ellipsis-elided and cross-speaker quotes explicitly.
Enforcement already handled this (locate() rejects non-contiguous spans); v2 aims to
get the model to emit the correct contiguous span so the golden edges survive rather
than being quarantined. Re-ingest under v2 will show whether recall recovers.

**Calibration note for the eval chapter:** all four quarantined edges carried
claimed confidence 0.90–0.97. The model was *most* confident on exactly the claims
whose evidence did not hold up. Self-reported confidence is anti-correlated with
correctness here — which is the entire argument for verification over trusting the
score.

**Also fixed:** `neo()` now waits for the Bolt handshake (a fresh container needs
~20-30s; `init` was racing the boot and dying with ConnectionReset).
