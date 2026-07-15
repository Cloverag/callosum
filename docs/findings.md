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

## 2026-07-15 (run 3) — RBAC leak through graph edge quotes. THE finding.

First clean end-to-end run (prompt v2). Q1 (Raj) produced a full, correct decision
answer. Q2 exposed a real security hole, which is the most valuable result so far.

**The leak.** Marcus (investor, clearance 1) asked "What is Priya's compensation?"
The vector side correctly withheld the confidential comp doc ("1 source withheld").
But the answer still stated "$185K base" — leaked through the GRAPH.

**Mechanism.** A `Priya —WORKS_AT→ Meridian Inc` edge — a benign relation — was
extracted from the sensitivity-3 comp chunk, and its verbatim evidence quote embedded
"She's at $185K base". `graph_search` filtered the vector chunks by clearance but
returned edge quotes with no check on the sensitivity of the chunk each edge came
from. RBAC was enforced on one store and not the other.

**Why it matters (thesis).** In a hybrid graph+vector system the permission filter
must be applied identically to both stores, and **edge provenance quotes are
themselves a leakage channel** — the relation type can be harmless while its evidence
span carries the secret. Filtering chunks is not enough; you must filter edges by the
sensitivity of their source chunk. Most GraphRAG systems have no RBAC at all and so
never encounter this; ours did because it enforces access, and that is the point.

**Fix.** `graph_search` now gates every edge on its source chunk, fail-closed:
`MATCH (src:Chunk {id: r.chunk_id}) WHERE src.sensitivity <= $clearance` (MATCH, not
OPTIONAL — an edge with no readable source chunk is withheld). This transitively
hides confidential-only entities too, since all their edges originate in confidential
chunks. Verified: Marcus's traversal from Priya no longer returns any salary edge;
Raj's still does; the end-to-end answer to Marcus is a clean refusal with disclosure.

**Note on Q1.** Raj's excellent answer came mostly from the vector passages; the graph
contributed only the 1-hop `ABOUT` edge, because the SUPPORTED/OPPOSED/APPROVED edges
hang off the *Decision* node, two hops from the *Topic* the planner extracted. This is
the concrete case for the deferred multi-hop traversal (#12) — the graph's relational
payoff needs >1 hop to surface on this question shape.

## 2026-07-15 (run 4) — clean end-to-end on fresh data. Milestone.

Full reset, prompt v2. Both golden queries correct:
- Q1 (Raj, clearance 4): complete decision answer — rejected for the 13-point margin
  hit and Series C narrative; Priya/Elena supported, Marcus opposed, Raj made the
  call; action item captured.
- Q2 (Marcus, clearance 1): "none of the accessible sources contain any information
  about Priya's compensation… one source was not retrieved due to clearance
  restrictions." The RBAC edge-gating fix holds on a graph it had never seen. No leak.

**New observation — fabrication is stochastic, not a fixed set.** Run 3 quarantined
one WORKS_AT edge; run 4 quarantined MADE_IN (0.90) and ATTENDED (0.96) — different
edges, same document, same model, same prompt. The ATTENDED at 0.96 came from the
comp doc, which only has two people present, so it invented an attendance at high
confidence. Implication for the eval: you cannot enumerate and patch "the" fabricated
edges, because they differ run to run. Runtime verification is not a nicety here — it
is the only thing that catches a failure you cannot predict. This strengthens the
confidence-anti-correlated-with-correctness result: 0.90–0.96 claimed on invented facts.

**Still true from run 3:** Q1's polarity came from the vector passages; the graph
contributed only the 1-hop ABOUT edge. The person→decision edges are 2 hops from the
Topic the planner searched. Vector RAG is carrying this question. Multi-hop traversal
is the next build — it is what makes the graph, not the vectors, answer the relational
questions the thesis claims are its advantage.
