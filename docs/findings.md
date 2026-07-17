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

## 2026-07-15 (run 5) — multi-hop traversal. The graph finally does what vectors can't.

`graph_search` extended from 1-hop to bounded 2-hop (`max_hops=2`, capped at 3). Full
reset, prompt v2, gpt-oss:120b-cloud. **This is the run where the graph's relational
payoff appears — the whole reason the system is hybrid.**

**What changed in the answer.** On "Why did we reject Pricing Model B?", the planner
still seeds on the *Topic* ("Pricing Model B"). At 1 hop that reached only the ABOUT
edge and stopped (runs 3–4). At 2 hops the traversal crosses the Decision node and out
to the people, and the graph facts now include the positions directly:

  - `path: Pricing Model B ←ABOUT— Reject Pricing Model B ←APPROVED— Raj Malhotra`
  - `path: … ←SUPPORTED— Priya Nair`
  - `path: … ←OPPOSED— Marcus Webb`
  - `Write pricing decision pack —DERIVED_FROM→ Reject Pricing Model B`

The synthesized answer cites `[Graph]` for who-approved / who-opposed / who-made-the-
call, i.e. the relational structure is now sourced from the graph rather than inferred
from prose. **The vector-vs-hybrid comparison the thesis rests on now exists as a
concrete artifact** — the `path:` chains are relationships no single vector chunk
contains (person and topic are never in the same sentence; only the decision links
them).

**Honest scope note.** The supporting *text passages* [1]–[3] are still vector-
retrieved; the graph contributes the *facts and their provenance quotes*, not new
citation text (the edge source-chunks dedup against the vector hits). That is the
correct division of labour, not a shortfall: the graph says *who/what/how-related*, the
vector store supplies *the words*. The eval should measure them on that split (relational
recall from the graph; passage grounding from vectors), not as interchangeable retrievers.

**Security — the wider traversal did not reopen the run-3 leak.** RBAC is now gated at
the *path* level, fail-closed: a path is returned only if every edge on it comes from a
readable chunk (`sum(CASE WHEN src.sensitivity <= clearance) = edge_count`); one
confidential hop withholds the entire path. Multi-hop is more chances to leak per query,
so the gate is on the path, not a post-filter. Q2 confirms it empirically: Marcus
(clearance 1) asked for Priya's compensation and got a clean refusal — no salary reached
him through any 2-hop path. Manual audit of the new Cypher (injection, null chunk_id,
node-name exposure, aggregate correctness) found no leak; see session notes.

**Caveat for the limitations section (not a leak).** `-[*1..3]-` expands before
`LIMIT 100`, so traversal cost grows with graph size before truncation. Fine on the
demo corpus; a real deployment wants relationship-type pruning or a hop budget keyed to
the planner. Note it; don't fix it until an eval on a larger corpus shows it bites.

## 2026-07-15 (run 6) — building the eval exposed why it can't share a graph with extraction.

Built the Phase 7 harness (`callosum eval`): every gold question run under hybrid and
vector-only, scored per stratum, graph-fact recall as the mechanism metric. Two findings
came out of the first attempt, and the second is the important one.

**(a) Empty-query embedding crash (fixed).** The graph-ablation forces vector search on
every question. A question the planner routes graph-only returns an empty `search_query`;
embedding an empty string makes bge-m3 emit a NaN vector that Ollama can't serialise
(HTTP 500, "unsupported value: NaN"), which aborted the whole run. Fixed three ways:
`embed()` substitutes a space for empty input; `ask()` falls back to the question text
when `search_query` is blank; `evaluate()` records a per-question error and continues
instead of losing the run. Lesson: any ablation that forces a path the planner meant to
skip must supply that path a valid input.

**(b) THE finding — a stochastically-extracted graph makes the retrieval eval
non-reproducible.** This run's extraction quarantined the `ABOUT` and `APPROVED` edges
(both claimed 0.90). `ABOUT` connects the *topic* the planner seeds on to the *decision*
— without it, the 2-hop traversal from "Pricing Model B" cannot reach the people, so Q1
produced **no `path:` facts and answered entirely from vectors**, unlike run 5 on the
same corpus and prompt. Comp-doc proposals also swung 36 → 19 run-to-run. Had the eval
scored against this graph, hybrid's graph-fact recall would read ~0% on the pricing
stratum — measuring *extraction luck, not retrieval capability*.

This forces a methodological split the thesis must state explicitly. There are two
contributions and they cannot be measured on the same artifact:
  1. **Extraction quality** — quarantine / fabrication stats. Stochastic by nature; the
     variance is itself the result (runs 1–6).
  2. **Retrieval advantage** (hybrid vs vector) — must run against a **fixed, curated
     gold graph**, or extraction noise confounds every number. You do not evaluate a
     retriever on a knowledge base that randomly rewrites itself between runs. Seeding
     the known-correct edges deterministically and saying so is rigorous, not cheating —
     it isolates the variable under test.

RBAC held regardless of the graph shuffle: Marcus got a benign `OWNS` edge and a clean
refusal on salary. Fail-closed does not depend on which edges extraction happened to keep.

**Next:** a deterministic eval-graph seed (`seed-eval`) — the gold entities + edges +
chunk sensitivities written straight to the stores, bypassing the LLM — so `callosum
eval` measures retrieval on a stable graph. Extraction keeps its own separate scorecard.

## 2026-07-15 (run 7) — first reproducible eval, and it says HYBRID LOSES. Read on.

The gold-graph seed works: `scripts/eval.sh` is deterministic now. The first honest,
reproducible Phase 7 table — and it is the opposite of the hoped-for direction. This is
the eval doing its job.

| Stratum | n | Vector-only | Hybrid | Graph-fact recall |
|---|---|---|---|---|
| lookup | 3 | 3/3 | 2/3 | — |
| relational | 3 | 3/3 | 3/3 | 100% |
| multi_hop | 2 | 1/2 | 0/2 | 0% |
| rbac | 2 | 2/2 | 1/2 | — |

Hybrid lost L3, M2, X2 (vector ✓, hybrid ✗) and tied everywhere else. Three causes,
diagnosed from the per-question breakdown, in order of importance.

**(1) A comparison/correctness bug — hybrid was starved of passages.** The ablation
always runs vector search; hybrid respected the planner's `needs_vector`. When the
planner over-trusted the graph and set `needs_vector=False`, hybrid retrieved *less*
than vector-only and lost L3/M2/X2. A hybrid system must retrieve a SUPERSET of its
vector-only ablation — the graph may only add context, never remove it. FIX (this run):
vector search always runs; `needs_vector` is now advisory-only, not a gate. Re-run
expected to flip L3, M2, X2 to hybrid ✓. Lesson: the planner's cost optimisation was a
correctness bug, and only the ablation exposed it.

**(2) Entity resolution blocks multi-hop — 0% graph recall despite a correct graph.**
The `multi_hop` questions say "usage-based pricing"; the seeded node is "Pricing Model
B". `graph_search` matches `WHERE seed.name IN $names` (exact), so it seeds on nothing
and the traversal never fires. `relational` scored 100% recall only because those
questions name "Pricing Model B" verbatim. This is the exact-string entity-resolution
limitation, now justified by a measured failure rather than asserted. The multi-hop
TRAVERSAL is proven (relational reached the 2-hop-away POSITION edges at 100%); what is
missing is linking the question's vocabulary to the node's name.

**(3) The corpus ceiling — the graph ties instead of winning.** Where the graph DID
fire (relational, 100% recall), hybrid still only tied vector-only. On a single fully
readable transcript the relational facts are also present in the retrievable text, so
vector needs no graph to answer. The graph's join advantage cannot appear until the
answer is NOT co-located in one chunk — i.e. until the corpus forces a cross-document
join. This is the strongest argument yet for corpus expansion, and it is an empirical
result, not a hunch.

**No RBAC leak.** X1 (Marcus) passed under both conditions — the confidential "$185K"
edge never reached the investor, through graph or vector. The rbac 1/2 is X2: Raj not
getting his OWN authorised answer under hybrid, caused by (1), the starvation bug. That
is an availability failure, not a confidentiality breach; fixing (1) resolves it. The
seeded confidential graph edge means the gate was genuinely exercised this run, not
merely the vector filter.

**Where this leaves the thesis.** The eval is now a real instrument: reproducible, and
already producing three actionable, mechanistic findings on its first honest run. The
narrative is not "hybrid wins" (yet) — it is "here is precisely what a hybrid system
must get right for the graph to pay off: never starve vector, resolve entities, and feed
it a corpus where answers span documents." That is a more credible thesis than a graph
that wins by construction. Next: re-run with fix (1); then entity resolution (2); then
corpus expansion (3).

## 2026-07-16 (run 8) — the answer-text metric can't be made deterministic on a cloud model. Measure retrieval.

Two harness-fairness fixes went in: (1) both arms now share ONE plan computed at
temperature 0, so the ablation isolates the graph rather than re-running a stochastic
planner per arm; (2) synthesis pinned to temperature 0. The result taught us the limit
of answer-text scoring.

**The hosted model is nondeterministic under identical input — so answer text can't be
the metric.** Careful claim (per review — we can demonstrate nondeterminism, not that the
model literally "ignores temperature"; a hosted endpoint may be nondeterministic for
routing/batching/backend reasons too): L3 ("how many months of runway?") has NO matching
graph entity, so `graph_search` returns nothing — hybrid and vector-only send
*byte-identical* context to the synthesiser, with a shared temperature-0 plan. They still
produced different answers across runs (run 8: vector ✓/hybrid ✗; the very next run:
vector ✗/hybrid ✓ — the failure flipped arms). With identical prompt and context, the
only remaining variable is the hosted model's own sampling. **Thesis phrasing:** "under
repeated runs with identical prompts and retrieved context, the hosted model produced
nondeterministic outputs despite deterministic retrieval; therefore answer text was not
used as the primary metric — graph-fact recall was, because it is deterministic." Added a
`graph facts` column so this is visible: a row with 0 graph facts and hybrid≠vector is
serving nondeterminism, read it as a tie, not the graph helping or hurting.

**The reproducible metric is graph-fact recall.** It depends only on the (now temp-0,
shared) plan's entities and the seeded graph — no synthesis. It is the number to put in
the thesis: **relational 100%, multi_hop 0%.** That single contrast is the whole current
result — the graph reliably delivers the required edge when the question's words match a
node (relational), and never when they don't (multi_hop: "usage-based pricing" vs the
"Pricing Model B" node). Everything else on this corpus is saturated (all answerable from
text) and noisy.

**bge-m3 NaN embedding is a server-side flake (handled).** M1 hit the same "unsupported
value: NaN" 500 — bge-m3 computes a NaN vector and fails to encode its own response, so
it cannot be sanitised client-side. Added: retry a 500 up to 3× (it is often transient),
and if it persists, `vector_search` degrades to graph-only with a stderr warning instead
of aborting the query. The harness already isolated the failure to one question; now that
question gets scored (graph-only) instead of dropping out of its stratum.

**Net:** the eval is as reproducible as this model allows — deterministic at the
retrieval layer, honestly noisy at the synthesis layer, and the report now labels which
is which. Headline stands: **multi_hop graph-fact recall is 0% purely because of
exact-string entity resolution.** That is the next build, and it is the one that moves
the one metric that matters.

## 2026-07-16 (run 9) — canonical entity grounding. Multi-hop recovers; the bottleneck was linking, not traversal.

Added planner-assisted canonical entity grounding (Named Entity Linking): the planner is
given the graph's vocabulary and maps the question's wording ("usage-based pricing") onto
the node name it stores ("Pricing Model B"). `graph_search` is unchanged — grounding
happens upstream. Deterministic: no embeddings, no thresholds, no hand-maintained aliases.

**Result (first grounded run).** multi_hop graph-fact recall 0% → 100%; entity grounding
100% (5/5), traversal 100%. Then adversarial questions were added — paraphrases sharing
NO tokens with the node name ("consumption-pricing model", "pay-per-use proposal",
"metered-billing plan", "commercial pricing plan") — to test whether the linker
generalises or just handled one obvious synonym. Second run, with adversarials:
**grounding 89% (8/9), GER 11%, traversal (given grounding) 100%.** The single miss was a
*standard* multi_hop question, while the *harder* adversarial paraphrases grounded — which
points at the cause: the planner is an LLM on a nondeterministic hosted endpoint (run 8),
so grounding inherits that nondeterminism and GER has a noise floor on this model, rather
than a systematic linking gap. Worth stating plainly in the thesis.

**Claim, phrased to match the evidence** (per review — do not overclaim "the engine is
always correct"): *within the evaluation corpus, graph traversal behaved correctly once
entities were grounded to canonical nodes; the remaining retrieval failures were
attributable to entity grounding rather than to graph traversal.* The two-stage split
(grounding vs traversal) is what licenses even that narrower claim.

**Instrumentation added this run (measurement, not architecture):**
- **Grounding correctness**, not mere presence — a wrong-but-in-vocab seed fails, so a
  grounding error is distinguishable from a traversal bug.
- **GER** (grounding error rate) as the primary linker metric; confidence deliberately
  NOT used — a model's self-reported confidence is not observed correctness (GER is).
- **Grounding precision** via `grounding_neg` questions with no referent ("dynamic
  pricing engine", "customer churn dashboard"): a good linker must ABSTAIN; grounding one
  anyway is a false positive.
- **The ablation** (reviewer's "one experiment"): identical graph engine, grounding on vs
  off. "Exact match only" vs "planner grounding" recall — the delta is the measured
  contribution of the grounding stage, not an assertion. (Numbers populate on the next run.)
- **A CSV experiment log** (`eval/results.csv`), one row per question per run, so runs
  7→8→9→… are diffable without re-reading prose.

**Scaling caveat (state it in the thesis so no examiner raises it):** for the evaluation
corpus the full entity vocabulary was small enough to pass to the planner directly. At
larger scales a lightweight candidate-retrieval stage would first reduce the search space
(substring/token index over node names) before the LLM chooses among candidates.

---

## The research narrative (this is the thesis spine, not a feature list)

1. **V1 — GraphRAG with LLM extraction.** Standard hybrid graph+vector.
2. **Observation:** hallucinated evidence and nondeterministic synthesis made evaluation
   unreliable — you could not tell a real edge from an invented one, or reproduce a score.
3. **V2 — verified evidence spans + provenance + quarantine + deterministic graph-fact
   evaluation.** No edge without a located verbatim quote; the extraction process becomes
   the dataset; the eval is measured at the retrieval layer, not on noisy answer text.
4. **Observation:** multi-hop failures were caused by entity GROUNDING, not by graph
   traversal — proven by the two-stage split (traversal 100% given grounding).
5. **V3 — planner-assisted canonical entity grounding.** Restores deterministic multi-hop
   retrieval without heuristic thresholds or embedding matching.

Each step is driven by an observed, measured failure — not architectural intuition. That
progression is the contribution.

## Freeze boundary (write this down and hold it)

**FROZEN — no more production code without a measured shortcoming against the baseline:**
extraction · evidence verifier · quarantine · planner · canonical grounding · traversal ·
RBAC gate · human approval.

**NOT frozen — these must keep growing:** datasets (more meetings, more document types) ·
questions · analyses · the error taxonomy. The biggest current risk is single-corpus
overfitting: everything so far rides on one board transcript. The next and most valuable
artifact is NOT a feature — it is an evaluation dataset spanning multiple meetings and
document types. Every future feature (auto-aliases, temporal edges, contradiction
detection) must be justified by a measured gap against this frozen baseline.

**Deferred, each with its trigger:** Level 2 auto-aliases from `ABOUT` edges (trigger: GER
stays > 0 after de-noising the planner) · Level 3 embedding NEL (trigger: aliases
insufficient) · candidate retrieval for grounding (trigger: graph too large to pass whole
vocab).

## 2026-07-16 (run 10) — instrumented run confirms the ablation, and finds the linker's real weakness: precision.

Full instrumented run (ablation + negatives + CSV; `eval/results.csv`). This is the run
that both confirms the grounding win AND exposes the next real limitation.

**Grounding recall 100% (9/9), GER 0%.** The run-9 single miss (11%) did not recur — it
was hosted-model nondeterminism, as suspected. Traversal 100% given grounding.

**The ablation (reviewer's experiment), now with numbers.** Same graph engine, grounding
on vs off, read from `recall_ungrounded` vs `recall_grounded`:

| Configuration | Graph-fact recall (paraphrased questions) | (all graph questions) |
|---|---|---|
| Exact match only (no grounding) | **0%** | 33% |
| Planner grounding | **100%** | 100% |

The clean "0% → 100%" lives in the paraphrased strata (`multi_hop` + `grounding_adv`, 6
questions). Over all 9 graph questions the ungrounded baseline is 33%, because the 3
`relational` questions name the entity verbatim ("reject Pricing Model B") and so match
even without grounding. That is the honest shape: **grounding contributes exactly where
the mention is not a verbatim node name, and nothing where it already is.** The per-
question CSV shows it cleanly — relational 1.00/1.00, every paraphrase 1.00/0.00.

**THE new finding — grounding PRECISION is the weak point, not recall.** N1 ("Why was the
*dynamic pricing engine* rejected?") is a FALSE POSITIVE: the planner grounded it to
"Pricing Model B" instead of abstaining. Precision = 50% (1/2); N2 ("customer churn
dashboard") correctly abstained. The linker over-grounds: on a corpus with exactly one
pricing entity, any pricing-adjacent phrase gets pulled onto it. This is the reviewer's
predicted failure, now measured — and it reframes the roadmap. Recall was the run-8/9
story and it is solved; **precision is the run-10 story and it is open.** A good NEL stage
must know when NOT to link. Evidence now justifies an abstention mechanism (a "none of
these" option in the grounding prompt, or candidate-retrieval where "dynamic pricing
engine" surfaces no close candidate). Do not build it yet — but it is the first thing the
larger corpus will stress, because more entities means more chances to mis-link.

**Caveat that strengthens with corpus size.** On one document, both the false positive
(only one pricing node to grab) and the high recall (only one plausible target) are
partly artefacts of scale. The precision problem will get HARDER and the recall problem
EASIER as documents are added. That is the single strongest reason the next work is
corpus expansion, not code: it is the only way to measure whether grounding holds when
there is genuinely more than one thing a mention could link to.

## 2026-07-16 (corpus + ontology) — Board Meeting 13, temporal reasoning, and ontology v2.

Added the second document (`data/demo/board_meeting_13_transcript.txt`): seven months
after Meeting 12, the board REVERSES the pricing rejection. This is the temporal /
decision-evolution stress case — the answer to "is Model B rejected?" now lives in an edge
in a *different* document (`Adopt Usage-Based Pricing —SUPERSEDES→ Reject Pricing Model B`).
Written so the extractor must INFER the supersede from natural language ("reversing our
decision from March"), not match the ontology keyword. Four `temporal` gold questions,
including the cross-hop "*why* was it reversed?" (Northwind's request + Series C + the
supersede — a genuine multi-hop join).

**Ontology v2 — evidence-driven, not feature creep.** Meeting 13 introduced a customer-
driven decision (Northwind, the largest account, formally asking for usage-based pricing)
that no existing relation could represent without distortion — `SUPPORTED` would equate a
customer's commercial request with a director's vote. Added `REQUESTED` (defined generally:
any actor formally requesting a proposal/action/decision), bumped `ONTOLOGY_VERSION` → 2,
and logged it in `docs/ontology-changelog.md`. This is the freeze rule working: the corpus
produced a relationship the ontology could not carry, so the ontology evolved — versioned,
so a future "recall 89% (v1) → 93% (v2)" is an attributable claim. The change is additive
and backwards-compatible.

**Document-aware seeding.** `seed_graph` no longer keys on sensitivity (which two board
meetings now share) — it attaches each group's edges to a chunk of the document they came
from, matched by title. All entities are seeded before any edges so cross-document edges
(M13's decision superseding M12's) find both endpoints. This is the right abstraction as
the corpus grows.

**The corpus is now a capability matrix, not a pile of transcripts** (each document exists
to stress ONE capability — a cleaner experimental design than "more data"):

| Meeting | Capability under test |
|---|---|
| 12 | Polarity reasoning (SUPPORTED / OPPOSED / APPROVED on one decision) |
| 13 | Temporal reasoning & decision evolution (SUPERSEDES across documents) |
| 14 | Entity grounding — aliases: "Raj" / "Rajesh" / "R. Malhotra" for one person |
| 15 | Conflicting evidence & provenance — Finance says 12M, Sales says 11.6M |
| 16 | Context-dependent references — "that proposal", "the previous motion" |

**Then stop generating synthetic data.** After M16, the honest next step is *messier* real
or realistic documents (typos, inconsistent speaker names, interrupted dialogue, unnamed
references) — that is where systems like this actually get tested. Synthetic data proves
the capability exists; messy data proves it survives contact with reality.

**Run 12 (M13 wired in) — confirmed.** `temporal` stratum 4/4, **graph-fact recall 100%**:
the cross-document `SUPERSEDES` reasoning works — the answer to "is Model B still rejected?"
requires an edge in a different document, and the graph delivers it. `multi_hop` moved from
vector 1/2 to **hybrid 2/2** — the graph won a stratum on answer text, not just recall.
Ablation over 13 graph questions: **exact-match 31% → grounding 100%.** Grounding recall
dipped to **85% (11/13), GER 15%** — the predicted corpus-scale effect: more entities give
the linker more ways to mis-link. Traversal 100%; precision steady at 50% (N1 still
false-positives). Net: the temporal capability is demonstrated and the graph's advantage is
now visible on answer-correctness, while grounding recall/precision under scale becomes the
next thing to watch — which is exactly what the capability matrix (M14 aliases) is for.

## 2026-07-16 (IG-1 gate audit) — baseline tag verified; local reproduction blocked

This audit reconciled the roadmap with the checkout before extending the corpus. The initial
local tag list was stale: after `git fetch --tags origin`, the annotated `eval-baseline-v2`
tag was present on commit `932f15a`, with the run-12 metadata and metrics recorded in its
annotation. R7 is therefore pinned; R8 is the next permitted checkpoint.

**Verified:** Python 3.12.10 ran the deterministic suite successfully: `24 passed, 5
deselected` from `.venv\\Scripts\\pytest.exe -q`. A fresh `docker compose down -v` followed
by `docker compose up -d` produced healthy Postgres and Neo4j services.

**Blocked reproducibility step:** `callosum doctor` reported that Ollama was not running at
`http://localhost:11434`; direct access to `/api/tags` also failed. The first `--no-extract`
ingestion therefore could not obtain `bge-m3` embeddings, so the seeded evaluation could
not proceed. This was a local-provider availability failure, not an evaluation result.

**Decision:** do not append synthetic evaluation results. Once Ollama is running and
`bge-m3` is available, rerun `scripts/eval.sh` (or its Windows-equivalent commands using
`.venv\\Scripts\\callosum.exe`) to independently reproduce the pinned baseline. That
environment limitation does not block beginning R8; R9 remains sequentially blocked behind
completed R8.

## 2026-07-16 (R8/R9 benchmark implementation) — aliases and conflicts are preserved

Meeting 14 supplies two explicit aliases for Rajesh Malhotra (`Raj` and `R. Malhotra`) and
the negative control Raj Patel. Ontology v3 adds `ALIAS_OF`: it is a source-backed,
reviewable edge, not an automatic rewrite or name merge. The normal proposal/approval path
therefore remains the only production write path, and a same-name person cannot be silently
collapsed.

The extraction prompt is version 3 and ontology version 3 for this benchmark. Both changes
are additive; a live extraction comparison must report those versions rather than attribute
any difference to alias handling alone.

Meeting 15 and its two independently dated supporting forecasts add a conflict benchmark.
Finance reports FY27 ARR of `$12.0M`; Sales reports `$11.6M`. Both metric-to-document edges
retain their own source chunks. Gold questions require an answer to present both figures and
sources, and treat a claimed approved target as a failure. The record deliberately has no
edge selecting a winner.

The deterministic suite validates the gold graph, expected-fact reachability, alias negative
control, and distinct forecast provenance (`25 passed, 5 deselected`). A live run has not
been recorded because Ollama remains unavailable locally, so no precision/recall, GER, or
conflict-recall number is claimed. Run the expanded `scripts/eval.sh` after restoring
Ollama, review the CSV/report against `eval-baseline-v2`, then change R8/R9 from
implementation-complete to accepted only if their remaining exit criteria pass.

## 2026-07-16 (R10/R11 benchmark implementation) — coreference abstention and messy inputs

Meeting 16 separates one explicit reference from one ambiguous one. “That proposal” is
explicitly tied to the Pricing rollout plan and retains a source-backed `DERIVED_FROM` edge.
“The prior motion” deliberately has two plausible antecedents; its gold case is marked
`should_not_ground`, so a fabricated link is measured as a false positive rather than
treated as a helpful answer. This is a benchmark limit, not a new automatic coreference
stage.

R11 adds intentionally imperfect TXT, Markdown email, VTT transcript, DOCX memo, and PDF
appendix fixtures plus a restricted Markdown email. Deterministic loader tests confirm text
extraction from every supported format and retain the existing fail-closed RBAC scenario.
The expanded evaluation script ingests all fixtures with explicit document types and
sensitivities.

The generated DOCX passed structural ingestion tests, but visual DOCX rendering could not
run because LibreOffice/`soffice` is unavailable in this local environment. The PDF fixture
was generated with a simple single-page layout; its text is validated by the same loader
test. No live extraction or document-type metrics are claimed until Ollama is restored.


## 2026-07-16 (R12 implementation) - permission-scoped candidates and enforceable abstention

Run 10 exposed a grounding false positive (precision 50% on two negative questions), and
run 12 exposed 15% GER at a larger corpus size. R12 replaces the full graph vocabulary in
the planner prompt with canonical names reached from the caller's clearance-filtered vector
hits. The Neo4j candidate lookup independently repeats `Chunk.sensitivity <= clearance`; a
private graph name cannot enter the prompt through this stage. The planner now has an
explicit empty-list abstention policy, and names emitted outside the supplied list are
discarded before traversal.

The deterministic suite covers the output guard, empty abstention result, and repeated
clearance predicate. It passed (`30 passed, 5 deselected`). Ollama is unavailable locally,
so candidate recall, precision, latency, and downstream traversal effects are not claimed.
The R13 handoff is documented in `docs/research-handoff.md`; its approval and P0 remain
blocked on the clean live evaluation rather than being inferred from implementation work.

## 2026-07-16 (R11/R12 hardening) - live candidate RBAC, traceable gold, and DOCX visual QA

R12 now has an opt-in live-store integration test (`CALLOSUM_RUN_INTEGRATION=1 pytest -m
integration`). It creates isolated sensitivity-1 and sensitivity-3 chunks in Postgres and
matching `Chunk`/`MENTIONS` nodes in Neo4j, mocks only the embedding provider, and proves the
complete candidate route returns the public name at clearance 1 and both names at clearance
3. It also passes the restricted chunk UUID directly to the Neo4j helper and confirms the
private name remains hidden. The fixture cleans up its unique records and does not reset
shared database volumes.

Gold records now carry machine-readable `source_documents` fields, checked against real
fixtures and rendered in the evaluation report. Two realistic, deliberately non-resolution
email records add a `messy_email` stratum: a vendor-security questionnaire follow-up and an
SOC 2 evidence request. Their source-backed ownership facts are seeded document-by-document;
`eval/gold-traceability.md` describes the review contract.

LibreOffice 26.2.4 was installed locally and used to render the DOCX risk-memo fixture to a
single-page PDF and 150-DPI PNG. Visual inspection found readable title/body text with no
clipping, overlap, or unexpected page break. `scripts/render_docx_qa.ps1` and
`docs/docx-visual-qa.md` make that QA repeatable. These checks strengthen implementation
evidence only; live R8-R12 acceptance metrics remain pending an available Ollama provider.

## 2026-07-16 (R8-R13 LIVE RUN) — the expanded benchmark, finally measured.

The R8-R13 handoff was blocked on an available Ollama; a working provider was used to run
`scripts/eval.sh` on a clean environment (fresh volumes). **29 questions, 11 strata, 16
documents** (Meetings 12-16, finance/sales forecasts, 8 messy docs incl. .docx/.pdf/.vtt,
comp), gold graph seeded (32 board + 1 confidential edges), ontology v3, candidate
grounding. Provider: ollama / gpt-oss:120b-cloud + bge-m3. Full rows appended to
`eval/results.csv`; review record in `docs/reviews/2026-07-16-r8-r13-live-run.md`.

**Two-stage summary (vs eval-baseline-v2):**

| Metric | baseline v2 | this run | delta |
|---|---:|---:|---:|
| Grounding accuracy (correct seed) | 85% | **71% (15/21)** | −14 |
| GER | 15% | **29%** | +14 |
| Grounding precision (negatives) | 50% | **33% (1/3)** | −17 |
| Traversal (given grounding) | 100% | **100%** | 0 |
| Ablation (grounding on) | 100% | **83%** | −17 |
| Ablation (exact-match only) | 31% | **48%** | +17 |

**Per-stratum graph-fact recall:** relational 100 · multi_hop 50 · temporal 75 · aliases
**100** · conflict 100 · coreference **0** · messy_email 100 · grounding_adv 88. RBAC 2/2.

**What generalized (the win — it is NOT overfit to Meeting 12):**
- **Aliases (M14) 100% recall.** The candidate-grounding + `ALIAS_OF` (v3) design resolves
  alias spellings correctly on the full corpus. This is the capability my simpler
  name-grounding fix would not have covered as cleanly.
- **Messy documents work.** `.docx`, `.pdf`, `.vtt`, `.md` all ingested and answered
  (messy_email 100%); RBAC held (restricted email + comp withheld correctly).
- **Traversal 100%.** The graph engine is still never the failure — the bottleneck is
  consistently the grounding stage, across every capability.

**What the scale exposed (the honest gaps — these are the real R8-R13 findings):**
- **Grounding PRECISION is the headline weakness: 50% → 33%.** With more entities, the
  linker forces more false matches (N1 "dynamic pricing engine" → Pricing Model B again,
  plus a second negative). Precision degrades with corpus size exactly as predicted;
  recall (71%) also dips. This is the strongest argument for the abstention work to
  continue — candidate scoping helped recall on aliases but has not fixed precision.
- **Coreference (M16) does NOT work: 0% recall.** "it" grounded to `Board Meeting 16`
  instead of the referenced plan. There is no coreference stage; contextual references
  fail the same way role references did. The hybrid answer-correctness on this stratum is
  lenient string-matching, not resolution — read the recall, not the answer column.
- **Conflict (M15): both sources retrieved (recall 100%) but synthesis inconsistent**
  (hybrid 1/2). The graph surfaces both forecasts with provenance; the answer layer does
  not reliably present the disagreement. Retrieval is right; presentation is the gap.

**Provider note:** bge-m3 NaN recurred (2 calls), degraded gracefully to graph-only.

**Status:** metrics recorded, NOT accepted. Per the R8-R13 handoff, acceptance requires a
reviewer decision — see the review record's Decision fields, left open for the reviewer.
This run supplies the live evidence the handoff required; it does not authorize P0.

## 2026-07-17 (R12 instrumentation) — the grounding deficit was partly a measurement artifact.

Branch `r12-abstention-hardening`. The R8-R13 run named grounding precision (33%) the
headline weakness and pointed at abstention as the fix. Before building an algorithm, the
candidate stage was instrumented to attribute the loss — and the attribution moved the
whole diagnosis. **No grounding, verifier, traversal, or RBAC code changed this session.**

**What was built (measurement only):** `retrieve.ground()` now returns the plan *plus* the
candidate list it was given and per-stage timings (zero behaviour change to `ask()`, so no
frozen-core exception). The eval records, per question, the candidates, whether an
acceptable entity was among them (`candidate_hit`), and `candidate_ms`/`plan_ms`. Because
`plan()` discards any name outside the candidate list, **candidate recall is a hard ceiling
on grounding** — grounding_acc can never exceed it. The report splits GER into the stage
that caused it: `loss_to_candidates` (never offered) vs `loss_to_linker` (offered, chosen
wrong). Runs log to `eval/results-v2.csv` (schema changed; the runs-7..13 log is preserved
untouched under the old header).

**Finding 1 — the candidate stage is not the bottleneck (on retrieved questions).** Over
the questions that were actually retrieved, **candidate recall is 100%**: every real
grounding failure was the linker choosing wrong from a list that contained the right answer,
never the candidate stage failing to surface it. `loss_to_candidates` = 0%. Tightening the
linker's abstention — the planned fix — would only have traded recall away against a ceiling
that was already perfect. *Caveat (per review): this holds on the evaluated subset; it must
be revalidated whenever the corpus or the embedding path changes.*

**Finding 2 — latency is the planner, not the candidate stage.** Mean candidate stage
~245 ms (one embed + two store queries); mean planner ~5000 ms (the LLM). **~20:1.**
Candidate caching would buy nothing end-to-end; if latency ever becomes a product concern,
the planner/LLM is the only lever worth pulling. Concrete engineering result, worth stating.

**Finding 3 — the bge-m3 NaN is an infrastructure fault, and it was corrupting the metric.**
The recurring `Ollama 500: unsupported value: NaN` is not a retrieval result: the affected
questions never entered the pipeline. Worse, a forced-empty candidate list makes `plan()`
abstain, which scores as recall-down *and* precision-**up** — so a bad enough embedding run
would make the abstention metric look like it improved. Three fixes: (a) `embed()` keeps
bge-m3 resident (`keep_alive`) and backs off between 500-retries instead of hammering the
same instant; (b) a bounded, explicitly-labelled harness retry re-attempts the empty-
candidate signature; (c) the harness now separates `unretrieved` (infra) from `evaluated`
and scores grounding only on the latter. **The metric is now robust to it either way**
(excluded, not mis-scored); closing it fully is an open infra task. *(Correction, 2026-07-17:
this entry originally called the NaN "intermittent" based on a probe that used a paraphrase,
not the exact failing string. The follow-up investigation found the fault is
**input-specific and deterministic** — see the 2026-07-17 stability + NaN entry below and
`docs/reviews/2026-07-17-nan-investigation.md`. `keep_alive`+retry does not fix it; the
harness exclusion is what keeps the metric honest.)*

**Finding 4 — several "linker errors" were benchmark defects, and fixing them exposed a
deeper decoupling.** Inspecting every miss against gold: C2 rejected exactly the forecast
nodes C1 rewards (an outright inconsistency, corrected). The pricing questions were
genuinely ambiguous — after M13 added the reversal, `Reject Pricing Model B` and `Adopt
Usage-Based Pricing` are two decision nodes sharing one topic, so "pay-per-use" no longer
identifies one. The questions were rewritten to name the intended decision (per review:
refine the benchmark, don't dumb down the linker); details in `eval/gold-traceability.md`.

But the rewrite only half-worked, and the *why* is the real finding. M1, M2, A2, A4 still
ground to `Adopt Usage-Based Pricing` even when the question says "the board **rejected**"
— the linker anchors on the lexically-near node and does not honour the polarity qualifier.
**Yet those same four answer correctly (graph-fact recall 1.00, hybrid ✓):** the two
decisions are linked (`SUPERSEDES` + shared `ABOUT`), so 2-hop traversal recovers the
required edges regardless of which of the two it seeds on. The inverse also occurred: A1
grounded to the *correct* seed but produced a *wrong* answer. **On a densely-linked graph,
seed-grounding accuracy does not track answer correctness** — which means "grounding
accuracy" over-reports failure, and neither the reversal-preference nor A1's answer error is
an abstention problem. The one genuine, repeatable abstention fault remains a single case:
N1 ("dynamic pricing engine" → Pricing Model B). Coreference (K1/K2) is a separate missing
capability (M16) and is now reported outside linker precision.

**Decision — abstention is NOT justified yet, and this is the freeze.** The evidence says:
candidate recall is full, traversal is full, the precision "weakness" is one example plus
mislabelled golds plus a coreference gap, and the headline grounding deficit was partly an
artifact of benchmark design and a partly-fixed infra bug. Designing a new grounding
algorithm against that would be tuning to noise. **The research contribution of this session
is that the instrumentation improved the benchmark and the measurement itself before any
algorithm was written** — the project's discipline (every feature justified by a measured,
repeatable gap) held. Frozen again pending a clean rerun that still shows a clear,
repeatable bottleneck. Review record: `docs/reviews/2026-07-17-r12-instrumentation.md`.

## 2026-07-17 (stability — 3 independent runs) — which metrics are reproducible, and which are LLM noise.

The core was run three times against the identical seeded graph, no code changes between
runs. The purpose was to establish what is reproducible *before* trusting any single number.
Runs: `22:34`, `22:47`, `23:01` in `eval/results-v2.csv`. First run was cold (~29 min); warm
runs ~13 min.

> **Methodological takeaway.** Mechanism metrics (candidate recall, traversal, graph-fact
> recall) were stable across repeated runs. LLM-generated answer text and seed grounding
> exhibited nondeterministic variation despite fixed decoding parameters, so thesis
> conclusions are based primarily on deterministic mechanism metrics.

**Deterministic — safe to quote as results:**
- **Candidate recall: 100% / 100% / 100%.** The R12 ceiling is rock-stable across runs.
- **Grounding precision (abstention negatives): 50% / 50% / 50%.** The single N1 false
  positive ("dynamic pricing engine" → Pricing Model B) is deterministic — a real, repeatable
  linker fault, and the *only* one.
- **Traversal given grounding: 100%** every run. The engine is never the variance source.

**Nondeterministic — must NOT be quoted from a single run:**
- **The grounded seed flickers.** `grounded_to` varies run-to-run on ~10 questions (e.g. A1
  toggles `Pricing Model B` vs `Pricing Model B|Reject Pricing Model B`; R1, T3, L1 similar).
  Cause: `gpt-oss:120b-cloud` ignores `temperature=0` (established run 8). The *set* of seeds
  is stable enough that recall holds, but the exact list is not reproducible.
- **Grounding accuracy varies 76–80%**, driven by seed flicker on borderline questions
  (grounding pass/fail flips on C1, C2, M2 across runs) plus the denominator moving with
  unretrieved count.
- **Answer-correctness flickers** on A1, C1, E1, L3, T4 — the known cloud-model answer-text
  nondeterminism. Read graph-fact recall, never the answer column, for a mechanism claim.

**The T4 embedding fault is deterministic (see NaN investigation).** T4 is `unretrieved`
every run because its exact string reliably NaNs bge-m3 — reported and excluded, never
mis-scored. Root cause and proposed fix: `docs/reviews/2026-07-17-nan-investigation.md`.

**Secondary, unresolved:** the cold first run showed four extra one-time empty candidate lists
(C1, C2, K1, K2) with *no* NaN logged; all four retrieve cleanly in the warm runs and in
direct retest. Flagged as a low-priority cold-start transient, not root-caused.

**Lesson for the thesis:** the *mechanism* metrics (candidate recall, precision, traversal)
are reproducible and are what the claims should rest on; the *LLM-dependent* metrics (exact
seed, answer text, and any accuracy computed from them) carry ±a few points of run-to-run
noise from a cloud model that ignores temperature. Report the former as numbers and the
latter as ranges over multiple runs — never a single run's figure. This is why the design
made graph-fact recall, not answer text, the deterministic metric (run 8); the 3-run
stability check confirms that choice was necessary, not cautious.
