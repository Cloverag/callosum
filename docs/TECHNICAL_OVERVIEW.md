# Callosum / Meridian — Technical Overview

**Status:** research track closed and frozen (`eval-baseline-v3`); product track frozen
at P3 (`f0f1504`, 2026-08-01).
**Scope of this document:** what the system is, why it is built this way, what was
measured, and what is not true of it.

Every number here is traceable to a file in this repository. Where a figure could not be
measured, this document says so rather than estimating it — that rule is the reason
several sections below read as admissions.

---

## 1. Problem statement

An organisation's decisions live in documents: board transcripts, memos, forecasts,
email threads. Six months later nobody can answer *"is that still our position?"*
without reading everything again.

The obvious fix — put the documents in a vector store and ask a language model — fails
in a specific and dangerous way. A retrieval-augmented model will answer confidently
whether or not the evidence supports it. For a search engine that is a bad result. For
a record of what a board decided it is a fabricated minute, and it is indistinguishable
from a real one.

Two failure modes matter here and neither is solved by better prompting:

1. **The answer is unverifiable.** A model asserts "the board approved the hire" and
   there is no mechanical way to check whether any document says that.
2. **Multi-hop questions are not similarity questions.** *"Who changed their position
   between the two meetings, and what did they change it to?"* requires connecting a
   decision in one document to its reversal in another. Chunk similarity does not
   express that relationship; it retrieves text that *sounds* related.

Callosum is a research engine that answers these by construction. Meridian is the
product built on it — a board operating system where every surfaced fact carries the
quote that evidences it.

---

## 2. Why verified graph + vector retrieval

### The central invariant

> **No relationship enters the knowledge graph without a verbatim quote from the source
> document that a machine has located character-for-character.**

An LLM proposes an edge and supplies the quote it claims supports it. `locate()` then
searches the source text for that quote. If it is not found, the edge does not exist —
it is quarantined, not stored, not surfaced, not summarised.

This makes fabrication a *storage* problem rather than a *prompting* problem. The model
is free to hallucinate; the hallucination cannot become institutional memory, because
the verifier is a string search and not a judgement call.

`locate()` is deliberately narrow. It tolerates whitespace reflow, case, and
typographic-vs-ASCII glyph differences — the ways a faithful quote's *bytes* differ from
the source. It tolerates nothing else. A paraphrase is treated as a fabrication.

The boundary is enforced at both ends:

- **Too permissive is a leak.** `locate()` originally joined tokens with `\s+`, which
  matches a newline, so a quote could be assembled across a blank line — from the end of
  one speaker's turn and the start of the next. That text appears verbatim in the
  document while never having been said by anyone. Fixed in PR #90: reflow is now
  matched *within* a block and never across one.
- **Too strict is silent data loss.** The same fix nearly shipped without `\r` in its
  whitespace class, which would have failed to locate every quote in a CRLF document and
  therefore silently dropped edges instead of erroring.

### Why the graph, specifically

The graph is not decoration on top of vector search. The measured contribution is
isolated by ablation, holding everything else constant:

| Configuration | Graph-fact recall on graph-dependent questions |
|---|---|
| Exact match only, no grounding | **38%** |
| Planner grounding enabled | **100%** |

*Same traversal code, same corpus, same questions.* The only variable is whether the
planner resolves a question's wording to a canonical node name before traversing.
(`eval/results.md`.)

The stratified comparison shows *where* the graph earns its place. Read the table by row
— the claim is in the shape, not the total:

| Stratum | n | Vector-only | Hybrid |
|---|---|---|---|
| lookup | 3 | 2/3 | 2/3 |
| relational | 3 | 3/3 | 3/3 |
| multi_hop | 2 | 2/2 | 2/2 |
| aliases | 4 | **1/4** | **2/4** |
| temporal | 4 | 3/4 | 3/4 |

Lookup ties, because a fact stated in one sentence is a similarity problem. Aliases
separate, because "R. Kumar" and "Rajesh Kumar" are the same person only if something
models identity.

### How this differs from ordinary RAG

| | Typical RAG | Callosum |
|---|---|---|
| What is stored | chunks + embeddings | chunks + embeddings **+ a verified edge graph** |
| Source of truth | the model's output | the located quote |
| Fabrication handling | prompt engineering, judge models | edge is refused at write time |
| Multi-hop | hope the chunks co-occur | explicit 2-hop traversal from a grounded seed |
| Access control | filter after retrieval, or not at all | clearance excludes rows **before** retrieval |
| Human role | none | **no AI output mutates memory without human approval** |

---

## 3. System architecture

Two stores, bridged by a shared UUID (ADR-001).

```
documents ──► ingest ──► chunks ─┬─► pgvector embeddings   (Postgres)
                                 │
                                 └─► extract ──► verify() ──► proposed_change
                                                    │              │
                                              quarantine      human approval
                                                                   │
                                                                   ▼
                                                    entities + edges (Neo4j)
```

- **Postgres** holds documents, chunks, embeddings (`pgvector`), the approval queue and
  the entire product domain. It is the system of record.
- **Neo4j** holds the entity/relationship graph. Every node carries the `workspace_id`
  in its MERGE identity.
- **The bridge is a shared chunk UUID.** A graph edge points back to the exact chunk its
  evidence quote came from, which is what makes a graph fact clickable through to source
  text.

**Why not one store.** Recursive traversal in SQL is possible and unpleasant; vector
similarity in Neo4j is worse. The cost of the split is that consistency must be managed
rather than assumed, which is why every Neo4j write originates from an approved
`proposed_change` row in Postgres (ADR-008, *Proposed* — the formal rebuild command is
not built).

### Retrieval path

1. **Pre-query** — the planner extracts entity mentions from the question.
2. **Grounding** — mentions are resolved to canonical node names. This is the measured
   bottleneck; see §9.
3. **RBAC gate** — the caller's clearance excludes rows *before* retrieval, in SQL and in
   Cypher. Fail-closed.
4. **Hybrid retrieval** — vector similarity over chunks, plus 2-hop traversal from the
   grounded seed.
5. **Synthesis** — the model answers from retrieved evidence, and every claim is
   returned with the quote it came from.

---

## 4. Research architecture (Track A — closed)

Fourteen checkpoints, `R0`–`R13`, accepted and frozen at tag `eval-baseline-v3`.

**The frozen five** (`CONTRIBUTING.md`): `src/callosum/ingest.py`, `extract.py`,
`retrieve.py`, `store.py`, `schema/postgres.sql`. These change only with a *measured*
result against the baseline. "It felt cleaner" is not a reason; "GER moved from X to Y
and here is the run" is.

The freeze is enforced, not merely stated:

- `tests/test_no_raw_cypher.py` fails the build if any code outside the query gateway
  opens a raw Neo4j session.
- Every change is gated by `callosum eval-mechanism` (§10), and `eval/mechanism.csv`
  must come back byte-identical.
- PR #86 — an "audit fixes" PR touching three of the five frozen files with no eval run
  — was closed as superseded, and its product-layer half re-landed separately.

**What the freeze bought.** During P3, 61 API operations, a client write path and a new
domain module were added, and `mechanism.csv` was byte-identical at the end. That is
mechanically demonstrable proof that the product was built *on* the engine rather than
*into* it.

---

## 5. Product architecture (Track B — P3 frozen)

`meridian/` is a separate package that depends on `callosum` as an ordinary import. The
boundary is real: the product never edits the engine.

| Layer | Contents |
|---|---|
| `meridian/*.py` | 10 domain modules — meetings, agenda, decisions, packs, minutes, resolutions, commitments, board members, audit, documents |
| `meridian/api/` | 10 routers (9 domain + `auth`), **61 operations** across 44 paths |
| `meridian/migrations/` | **17** Alembic migrations, `0001`–`0017` |
| `frontend/` | Next.js 16 + React 19 + Tailwind v4, **12 pages** (the build reports 14 routes, counting `/_not-found` and `/icon.svg`; `/` is a config redirect, not a page) |

Aggregates were delivered one per checkpoint, each with its own migration, domain module
and tests. Every mutable aggregate carries a `version` column and optimistic concurrency.

### The 1:1 API rule (ADR-014)

Each public domain function gets one endpoint, shaped as the function is — minus
`workspace_id` and `clearance`, which are never accepted from a client.

The cost is stated rather than discovered later: 1:1 leaks the domain model into the
wire format, and a screen needing four aggregates makes four round trips. Neither bites
at this scale — one frontend, same origin, no external consumers — and building a
composition layer against imagined screens would be designing without evidence.
Revisit at P6.

### What the mock swaps found

The frontend's `lib/*.ts` modules were written to mirror the Python dataclasses field
for field, so each swap should have been a change of transport. **Six of seven found a
contract defect instead:**

1. `include_inactive` — invented, *and* lossy: it collapsed a tri-state
2. three phantom `Meeting` fields (`agenda`, `objectives`, `sensitivity`)
3. a nullable scheduling window declared as required
4. `clearance` accepted as a *client* argument on packs
5. `board_member_id` declared in TypeScript and silently dropped by `_row_to_stance`
6. the packs page joining **real** `document_id`s against a **mock** — every item in
   every pack rendered "Document reference could not be resolved"

Each is now pinned by a cross-language test that reads the TypeScript and compares it to
the Python.

**`commitments` was the one clean swap, and the reason generalises:** it is the only
mock written *after* its domain shipped. Every defect above came from a mock authored
before the Python existed. Write the domain first and the swap is transport; write the
mock first and it is a negotiation.

---

## 6. Authentication and authorization

Six ADRs (009–014), all owner-approved, all built.

- **OIDC** (Keycloak), session as an **httpOnly signed cookie**.
- **Identity maps on `(provider, subject)`**, never email — email is mutable and
  reassignable.
- **An unknown subject is rejected**, never auto-provisioned. Authenticating proves who
  you are, not that you belong here.
- **Workspace is selected explicitly and re-validated on every request.**
- **`workspace_id` and `clearance` are session-derived and never accepted from a
  request** (ADR-013).

That last rule is enforced mechanically rather than by review. `tests/test_openapi_input_guard.py`
walks the generated OpenAPI schema — following `$ref`s into request bodies — and fails
the build if any operation declares either name, in any spelling, including as a header.

The reasoning is that code review is the wrong instrument: an endpoint accepting a
`workspace_id` filter looks entirely ordinary, and the harm is invisible at the call
site. `GET /api/resolutions?workspace_id=<someone else's>` would be honoured, because
the database was told to trust the GUC.

### Tenancy, in three layers

1. **Postgres RLS**, `ENABLE` + `FORCE`, with the runtime connecting as a non-superuser
   role that cannot bypass it.
2. **Neo4j has no RLS**, so `workspace_id` is baked into entity MERGE identity and every
   read is scoped. All access goes through a single query gateway; raw sessions are
   banned by test.
3. **Composite foreign keys** where the constraint would otherwise operate below the
   isolation boundary — Postgres validates FKs as the table *owner*, bypassing RLS, so a
   single-column reference can link two tenants through a constraint neither can read
   across. Reproduced, then fixed.

### Clearance

A five-level ladder (public → restricted) resolved from the caller's **active
membership** on every request, fail-closed: no membership resolves to nothing at all,
not to a default.

Two fail-open defects were found and fixed here, and both are instructive because both
*looked* correct:

- `clearance: int = 4` as a default — `4` is the top of the ladder, so any caller who
  forgot the argument received everything. Now required, so a forgotten argument is a
  `TypeError` at the call site rather than a silent disclosure.
- `PUBLIC_CLEARANCE = 1` — `1` is *investor*. A caller asking for "public" was handed
  investor material, from a constant introduced to prevent exactly that class of error.

---

## 7. Evidence verification and withholding

### Provenance

Every graph fact carries a machine-checked verbatim quote and the document it was
located in. Surfaces render the quote, not a summary of it.

This is a rule the codebase has broken and had to fix — twice. During the CP-E audit,
all five "approved facts" on the dashboard were checked against `data/demo/` and **none
of the five quotes existed in any document**; two of the named sources were not
documents at all. They rendered under the heading *"Evidence, not summaries — each with
its source quote."* They are now derived from the generated graph data, so a quote
cannot be authored by hand. The same defect had been found and fixed in the assistant's
citations earlier; this surface was missed.

The lesson recorded from it: **the invariant holds in the engine and has to be
re-established at every surface.** A verifier that guards the graph does not guard a
literal typed into a React component.

### Withholding

Content above a caller's clearance is excluded *before* retrieval. What is disclosed
about the exclusion depends on what the contract can support, and the two live examples
are deliberately opposite:

- **`/memory` discloses a count** — "1 entity and 1 relationship withheld" — because
  `graph_search` returns one.
- **Board packs disclose nothing** — because `_fetch_items_for_packs` filters and then
  *renumbers from 1*, leaving no gap and no total. A notice that appeared only when
  something was hidden would itself be a disclosure: it would tell a reader the board
  discussed something excluding them. So the notice is a *standing* property of the
  card, and an all-withheld pack renders identically to an empty one.

Both are right; the contracts differ. The withholding discipline is tested to survive
the *write* path too — a low-clearance member editing a pack gets back a filtered
response, renumbered, with no count.

---

## 8. Evaluation methodology

The evaluation is the source of truth for any claim about the engine.

**Stratified, not aggregate.** 30 gold questions across 11 strata (lookup, relational,
multi-hop, temporal, aliases, conflict, coreference, messy_email, grounding_adv,
grounding_neg, rbac). The strata exist so that a total cannot hide a shape: a system
that is excellent at lookup and useless at multi-hop scores respectably on average.

**Two tiers, deliberately separated:**

| Tier | Depends on an LLM? | Purpose |
|---|---|---|
| **Verified** — candidate recall, traversal, RBAC | No | deterministic; the CI gate |
| **Observed** — grounding, precision | Yes | reported, never gated |

Security verification must never depend on a cloud model. The split also means a 429
from a provider cannot block a merge.

**Grounding is scored for correctness, not presence** — the right seed, not merely a
seed. **Traversal is measured only on questions that grounded**, which isolates the
graph engine from the linking stage above it. Without that split, a linking failure
reads as a graph failure and the wrong component gets optimised.

**The adversarial stratum is the honest one.** `grounding_adv` uses paraphrases that
share no tokens with the node name — "metered billing", "pay-per-use" for "Pricing
Model B" — so it tests generalisation rather than one lucky synonym.

---

## 9. Experimental results

Run 2026-07-20, `ollama` / `gpt-oss:120b-cloud`. Source: `eval/results.md`.

### Where retrieval succeeds and fails

| Stage | Result |
|---|---|
| Candidate recall — right entity offered to the planner | **100% (21/21)** |
| Entity grounding — correct seed chosen | **81% (17/21)** |
| Grounding Error Rate (GER) | **19%** |
| Traversal — given correct grounding | **100%** |
| Grounding precision — abstention on questions with no referent | **50% (1/2)** |

### The finding that redirected the work

**The multi-hop bottleneck is a Named Entity Linking problem, not a graph problem.**

Candidate recall is 100%: the right entity was offered to the planner every single time.
Traversal is 100%: given a correct seed, the graph returned every required edge. All 19%
of the loss sits in one stage — the linker choosing the wrong entity from a set that
contained the right one.

| Attribution | Share of 21 graph questions |
|---|---|
| Entity never offered to the planner | **0%** |
| Entity offered, linker chose wrong | **19%** |

This was worth more than the ablation number. The intuition before measuring was that
multi-hop traversal was weak; instrumentation showed traversal was perfect and the
failure was upstream. A planned abstention algorithm was **not built** as a result — the
measurement removed the reason for it.

**GER is deliberately not reported as a separate metric alongside grounding accuracy.**
Reading the code shows GER = 1 − grounding accuracy; plotting both double-encodes one
measurement.

### Known open weakness

**Grounding precision is 1/2.** When a question has no referent in the graph at all, the
correct behaviour is to abstain, and the linker does not reliably refuse. This is stated
here because it is the weakest number in the evaluation and it has not been fixed.

---

## 10. The mechanism gate

`callosum eval-mechanism` — deterministic, no cloud LLM, run before anything ships.

| Check | Required | Result at P3 freeze |
|---|---|---|
| Candidate recall | = total | **22/22** |
| Traversal recall (gold seeds) | = 100% | **21/21, 100% mean** |
| RBAC fail-closed | = total | **1/1** |

Each run appends to `eval/mechanism.csv`, and **the appended rows must be byte-identical
to the previous run.** A diff is a real regression, not model noise.

That property is what makes the gate useful rather than ceremonial. When `locate()` was
changed in PR #90 — a frozen-core change to the definition of "verified" — the gate
passed *and* the rows were identical, which is the evidence that the accepted-input set
narrowed without a single retrieval outcome moving. Behaviour unchanged, plumbing
changed. No amount of code review demonstrates that.

---

## 11. Security model

**Threat model, stated plainly.** This defends against application bugs and
authorization mistakes. It does **not** defend against a compromised database role:
`app.workspace_id` is an ordinary Postgres GUC, so RLS guards the application, not an
attacker with the connection string.

| Control | Mechanism | Enforced by |
|---|---|---|
| Tenant isolation (SQL) | RLS `ENABLE` + `FORCE`, non-superuser runtime role | database |
| Tenant isolation (graph) | `workspace_id` in MERGE identity, single query gateway | test-enforced |
| Cross-tenant FK linking | composite `(id, workspace_id)` foreign keys | database constraint |
| Clearance | resolved from active membership, fail-closed | `identity.resolve_principal` |
| Request cannot name its own scope | OpenAPI schema walk | build failure |
| No AI write without approval | `proposed_change` queue | schema |

**Existence oracles are treated as leaks.** "No such document" and "a document you may
not read" return the same 404. "You were never a member", "your membership was revoked"
and "that workspace is not yours" return one uniform 403. Distinguishing them would
confirm what exists to someone who cannot see it.

**The security findings that mattered were found by probing, not reading.** The
empty-`membership` discovery and the FK-bypasses-RLS finding both came from constructing
an attack and running it. Both looked correct in review.

---

## 12. Engineering decisions

15 ADRs in `docs/ARCHITECTURE_DECISIONS.md`. The ones that shaped the system most:

| ADR | Decision | Why it mattered |
|---|---|---|
| 001 | Two stores bridged by a shared chunk UUID | makes a graph fact traceable to source text |
| 005 | Deterministic frozen evaluation as the acceptance gate | security verification never depends on a cloud LLM |
| 006 | Verified provenance; research core frozen | changes need measurement, not intuition |
| 008 | Postgres canonical, Neo4j a rebuildable projection | **Proposed, not built** — recorded as design-only |
| 010 | Identity on `(provider, subject)`, never email | email is mutable and reassignable |
| 013 | `workspace_id`/`clearance` session-derived, schema-enforced | turns a review habit into a build failure |
| 014 | API mirrors domain functions 1:1 | each mock swap becomes transport, not negotiation |

### Working rules that produced the above

- **One verified change per commit.** The smallest change that increases confidence.
- **Measure before refactoring** — let the problem pick the work.
- **Record exceptions with an owner and a due checkpoint.** Three phases of work were
  deferred this way (CP9 → P8, CP-F/G/H → P9, graph/assistant → P6) rather than quietly
  dropped or hastily half-built.
- **Do not close a checkpoint by adding an empty table.** A deferral that is recorded is
  complete; a table nothing writes to is debt that looks like progress.

### Delivery statistics

| | |
|---|---|
| Commits on `master` | **305** (252 / 53 split between two contributors) |
| Python (engine + product) | ~13,400 lines |
| TypeScript (frontend) | ~9,700 lines |
| Migrations | 17 |
| Backend tests | **610** passing |
| Frontend tests | **180** passing |
| Findings log | `docs/findings.md`, 776 lines |

---

## 13. Limitations

Stated in full, because a limitation an evaluator finds is worse than one they are told.

1. **The corpus is entirely synthetic.** 16 authored files about a fictional company;
   10 seeded into the gold graph (38 entities, 40 edges, 14 relation types). No real
   organisational documents have ever been ingested. `docs/findings.md:481` names messy
   real documents as the honest next step and that step has not been taken.

   **This is the single biggest threat to the results**, and there is direct evidence it
   matters: the CRLF defect in PR #90 would have silently dropped edges from every
   Windows- or email-sourced document, and it survived 461 tests and a green mechanism
   gate because **no file in `data/demo/` uses CRLF.** The corpus cannot exercise the
   bug.

2. **P3 is frozen, not accepted.** Of its three exit criteria, one is met, one is
   partial, one is not met. The product track stands at **3 of 13 phases accepted**.

3. **Accessibility is designed, not audited.** The design system was built to WCAG 2.2
   AA and `rules.md` §6 holds it as a hard floor, but CP-G (keyboard and a11y smoke
   checks) was deferred. Deferring CP-G defers the *verification*, not the standard —
   and no accessibility claim in this project should be made without that qualifier.

4. **CP-F and CP-G were intentionally deferred** (#93), with CP-H, to P9. Failed and
   loading states are handled on five surfaces but have no systematic treatment.

5. **Composite-FK protection covers 1 relationship of 10** (#41). The rest are safe by
   convention — an RLS-scoped existence check in Python — which is a real defence that
   every future author has to remember.

6. **`graph` and `assistant` are snapshots, not live reads** (#100). Both show real
   data derived from the gold graph; neither is wired to the engine at runtime.

7. **Grounding precision is 50%** on abstention negatives. The linker does not reliably
   refuse a question with no referent.

8. **No CI.** Every verification in this document is a local run against real Postgres
   and Neo4j. There is no automated gate on pull requests.

9. **Single-corpus, single-run figures.** The evaluation numbers come from one corpus
   and, for the LLM-dependent tier, one run of one model. Multi-run stability has not
   been characterised.

---

## 14. Future work

In the order the evidence argues for, not the order that is most interesting.

1. **Real, messy documents.** The named biggest risk. Typos, inconsistent speaker
   labels, interrupted dialogue, unnamed references — and CRLF line endings. Expect the
   numbers to move; a drop is a finding, not a failure.
2. **Grounding precision.** The one clearly weak measurement. Abstention on
   no-referent questions is a linker problem with a measured 50% failure rate.
3. **Multi-run stability.** Report variance, not a single run, for the observed tier.
4. **CP-F/G/H** — loading and error states, an accessibility audit, the P3 exit gate.
   These are the difference between P3 frozen and P3 accepted.
5. **Composite FKs across all tenant-scoped relationships** (#41), replacing convention
   with construction.
6. **P6** — live graph and assistant reads, which need the withheld-count contract
   reproduced server-side, a layout strategy, and a Neo4j traversal performance answer.
7. **ADR-008's rebuild command** — replay approved changes into Neo4j, making
   inconsistency self-healing. Designed, not built.

---

## Appendix — reproducing the evidence

```bash
docker compose up -d
uv pip install -e ".[dev]"

# The deterministic gate. No cloud LLM.
.venv/bin/callosum eval-mechanism

# Full gated suite against real Postgres and Neo4j.
CALLOSUM_RUN_INTEGRATION=1 .venv/bin/python -m pytest

# Frontend.
cd frontend && npx jest && npm run build
```

| Claim in this document | File |
|---|---|
| Ablation 38% → 100%, stratified scores, GER attribution | `eval/results.md` |
| Mechanism gate rows | `eval/mechanism.csv` |
| Gold questions and traceability | `eval/gold.jsonl`, `eval/gold-traceability.md` |
| Running findings log | `docs/findings.md` |
| Architecture decisions | `docs/ARCHITECTURE_DECISIONS.md` |
| P3 freeze evidence | `docs/reviews/2026-08-01-p3-freeze.md` |
| Frozen-file list and contribution policy | `CONTRIBUTING.md` |
