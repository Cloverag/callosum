# Meridian / Callosum Roadmap and Completion Gates

This is the single authoritative development roadmap. It replaces the former
`path_to_completion.md`. `FEATURES.md` is a non-binding feature catalog; a feature is
not committed or “done” unless this roadmap assigns it to a checkpoint and the checkpoint
exit criteria are met.

## Operating rule

Work is strictly sequential. Start the next checkpoint only after the current one passes
every exit criterion, its evidence is reviewed, and any exception is recorded with an
owner and due checkpoint. A merged PR, prototype screen, or plausible demo is not enough.

Every checkpoint produces a decision record, risk-appropriate tests (including negative
security cases), updated docs/status, runnable verification commands, and a reviewed diff.
No checkpoint may weaken evidence verification, human approval, RBAC, provenance, or audit
requirements.

## Current progress — 2026-07-16

| Track | Completed | Active | Remaining |
|---|---:|---|---:|
| Research engine | **8 / 14** accepted (`R0`–`R7`) | **R8–R11** — benchmark implementation awaiting live evaluation | 2 capabilities (`R12`–`R13`) after R8–R11 acceptance |
| Meridian product | **0 / 13** accepted | Not started; blocked by research handoff `R13` | **13** (`P0`–`P12`) |

The counts must not be combined into one percentage: the research track validates the
memory engine; the product track makes it a deployable board operating system. The CLI
research foundation exists, but the product has no web application, workspace/meeting
domain, production identity, integration layer, or pilot yet.

### Integrity correction

`R7` is represented by Meeting 13, ontology v2, temporal gold questions, findings run 12,
and the annotated `eval-baseline-v2` tag on commit `932f15a`. A local clone that lacks this
tag must fetch tags before auditing progress. The next permitted checkpoint is **R8**.

**Latest gate audit (2026-07-16):** the fast suite passed under Python 3.12.10
(`.venv\\Scripts\\pytest.exe -q`: 24 passed, 5 deselected). Fresh Postgres and Neo4j
services started successfully, but a fresh local reproduction could not proceed because
Ollama was unavailable at `http://localhost:11434`. This is a local-environment limitation,
not a defect in the already-pinned R7 baseline.

---

# Track A — Verified institutional-memory research engine

## Completed research checkpoints

| ID | Capability | State | Evidence |
|---|---|---|---|
| R0 | Hybrid graph + vector architecture joined by shared chunk UUID. | ✅ Complete | `docs/architecture.md`, schema, `store.py` |
| R1 | Loading, hash-dedupe, offset-preserving chunking, embeddings. | ✅ Complete | `ingest.py`, deterministic offset tests |
| R2 | Verified extraction: every edge needs a located quote; invalid edges are quarantined. | ✅ Complete | `extract.py`, tests, findings runs 1–4 |
| R3 | Postgres/pgvector and Neo4j storage connected by shared UUID. | ✅ Complete | schema, `store.py` |
| R4 | Hybrid retrieval with pre-query, fail-closed RBAC. | ✅ Complete | `retrieve.py`, confidential test case, findings run 3 |
| R5 | Multi-hop traversal and canonical entity grounding. | ✅ Complete | retrieval/evaluator grounding-traversal split |
| R6 | Stratified reproducible evaluation: gold graph, ablation, GER, precision, CSV log. | ✅ Complete | `evaluate.py`, gold set, `eval-baseline-v1` |
| R7 | Temporal reasoning: `SUPERSEDES` across documents and ontology-v2 `REQUESTED`. | ✅ Complete | Meeting 13, temporal gold cases, findings run 12, `eval-baseline-v2` |

## IG-1 — Reconcile and pin the V2 baseline

**Goal:** Make R7 reproducible before changing the research core again.

**Work:**

- Run the documented evaluation under Python 3.12 with Meetings 12/13 and confidential
  corpus, using a clean local database.
- Record commit SHA, provider/model, prompt, ontology, corpus, temporal results,
  grounding metrics, and RBAC results; append the experiment CSV.
- Compare the result to run-12 claims. Create annotated `eval-baseline-v2` only if it
  truthfully represents the reproducible run; otherwise correct the historical claim.

**Exit checklist:**

- [ ] Fast deterministic tests pass in the supported Python 3.12 environment.
- [ ] A clean environment reproduces the seeded evaluation from documented commands.
- [ ] Temporal and RBAC cases run and their results are recorded.
- [ ] The V2 tag exists with truthful evidence, or the prior tag claim is corrected.

## R8 — Entity aliases and resolution policy — implementation complete; live measurement pending

**Goal:** Measure and safely handle one entity appearing as “Raj”, “Rajesh”, and
“R. Malhotra” without silently merging different people.

**Work:** add Board Meeting 14; add alias, same-name, and abstention gold cases; define a
reviewed alias/merge policy; compare exact matching, reviewed aliases, and planner
grounding.

**Exit checklist:**

- [x] True aliases and false merges are distinguishable in corpus and gold set.
- [x] Alias links retain evidence and human-review provenance.
- [ ] Precision, recall, GER, and false positives are measured against IG-1 (requires Ollama).
- [x] Existing graph facts retain source attribution and meaning.

## R9 — Conflicting evidence and provenance — implementation complete; live measurement pending

**Goal:** Preserve conflicts instead of inventing a single answer.

**Work:** add Meeting 15 and supporting sources with materially conflicting facts; add
gold cases requiring both claims, source/date context, and explicit uncertainty.

**Exit checklist:**

- [x] Both claims remain independently sourced and permission-filtered.
- [x] Gold cases require both claims and prohibit an unsupported approved target.
- [ ] Conflict recall and unsupported-resolution failures are reported (requires Ollama).

## R10 — Context-dependent references and coreference limits — implementation complete; live measurement pending

**Goal:** Safely resolve or abstain on references such as “that proposal” and “the prior
motion.”

**Work:** add Meeting 16 with references, distractors, and ambiguity; isolate whether
chunk context, graph context, or a reviewed coreference stage fixes a measured gap.

**Exit checklist:**

- [x] Ambiguous references have a no-link / needs-review gold case.
- [x] Correct links retain original source spans.
- [x] Evaluation has a distinct `coreference` stratum; live failure rates remain pending.

## R11 — Messy-document benchmark — implementation complete; live measurement pending

**Goal:** Test the engine beyond clean synthetic transcripts.

**Work:** add realistic typos, interrupted dialogue, inconsistent names, long sections,
emails, tables, PDF/DOCX fixtures, and confidentiality cases; build a hand-reviewed
benchmark by document type.

**Exit checklist:**

- [x] TXT, Markdown, VTT, DOCX, and PDF fixtures load in deterministic tests; restricted Markdown is included for RBAC setup.
- [ ] Results by document type and failure reason require a live extraction/evaluation run.
- [x] Fixture assertions and the local rendering limitation are documented.

## R12 - Grounding abstention and scalable candidates - implementation complete; live measurement pending

**Goal:** Make entity linking precise at larger graph sizes.

**Work completed:** semantic candidates now come only from chunks returned by the
clearance-filtered vector search. Neo4j repeats the chunk-clearance predicate before their
canonical names enter the planner prompt. The planner is explicitly instructed to abstain,
and its output is restricted to the supplied candidates as a runtime guard.

**Exit checklist:**

- [x] No-referent cases are first-class: the planner contract permits an empty entity list and model output outside the candidate set is discarded.
- [x] Candidate selection is permission-scoped and deterministic coverage verifies its clearance predicate.
- [ ] Candidate recall, grounding accuracy, false positives, latency, and downstream traversal effects require a clean live evaluation and review against `eval-baseline-v2`.

## R13 - Research handoff and frozen baseline - handoff prepared; approval pending

**Goal:** Close the research phase with a reproducible contract for product work.

**Work completed:** `docs/research-handoff.md` consolidates reproducible commands, the
named baseline, capability/evidence/limitation matrix, frozen-core exception process, and
the decision rule for P0. It deliberately records that live measurement is unavailable
rather than treating implementation work as acceptance.

**Exit checklist:**

- [x] The handoff lists commands, corpus/evidence references, and limitations for every implemented capability.
- [x] The freeze boundary and exception record are documented.
- [ ] R8-R12 require a live, reviewed evaluation before the handoff can be approved.
- [ ] `AGENTS.md`, `PRD.md`, `CONTRIBUTING.md`, findings, and roadmap may be declared fully aligned only at approved handoff; current documents consistently record the pending gate.
- [ ] Product checkpoint P0 requires explicit authorization after the approved handoff.

---

# Track B — Meridian Board Operating System

This track begins only after R13. It turns Callosum’s verified memory engine into the
founder-facing board workflow specified in `PRD.md`.

## P0 — Product contract and delivery controls

**Goal:** Make the PRD executable.

**Work:** assign product, engineering, security, and pilot owners; create requirements
traceability; set decision-log/change-control rules; lock pilot segment and V1 scope.

**Exit:** every V1 requirement has owner, priority, dependency, and testable evidence;
human-control/evidence/RBAC invariants are signed off; no static prototype is called built.

## P1 — Production security, tenancy, and governance design

**Goal:** Define access, retention, and processing rules before real board data enters a
web application.

**Work:** specify tenancy, identity, role/object policy, invitation lifecycle, audit,
retention/deletion, consent, encryption, secrets, backups, incident response, processors,
and residency; evolve clearance-only retrieval to reviewed object-level policy.

**Exit:** security approves threat/data-flow models and role matrix; unauthorized content is
blocked in SQL, Cypher, quotes, chunks, logs, APIs, and UI; transcript policy is approved.

## P2 — Durable product domain and migrations

**Goal:** Model the board workflow absent from Callosum.

**Work:** migrate workspace, member, board, meeting, agenda/pack/minutes versions,
decision, resolution, commitment, notification, and audit objects; define lifecycle states,
publication/version semantics, ownership, and retries.

**Exit:** migration/recovery plan is tested; invalid transitions and cross-workspace access
are rejected; superseded/published records preserve immutable history.

## P3 — Authenticated API and accessible application shell

**Goal:** Provide a secure founder-facing interface over approved core functions.

**Work:** select/document stack; build sign-in, workspace selection, role-aware navigation,
dashboard, directory, withheld/error/loading states, secure API contracts, rate limits, and
observability.

**Exit:** users access only authorized workspaces; UI distinguishes draft/approved/withheld/
failed states; primary flows pass keyboard and accessibility smoke checks.

## P4 — Board workspace, members, and source intake

**Goal:** Establish a single source of truth for board participants and material.

**Work:** implement members, document intake/import, metadata/sensitivity, versions and
duplicates, processing/quarantine state, and workspace/meeting assignment.

**Exit:** membership is authorized/audited; document lifecycle is visible; restricted titles,
text, quotes, graph facts, and hints cannot leak.

## P5 — Meeting, agenda, and board-pack lifecycle

**Goal:** Enable a founder to prepare and publish a permissioned pre-read.

**Work:** build meeting lifecycle, attendance/objectives, agenda editing/timeboxes,
evidence-backed agenda draft, pack assembly/review/version/publish, and explicitly
confirmed calendar/email adapters.

**Exit:** a meeting reaches a versioned published pack; review identifies missing/stale
material and unresolved commitments; publishes and sends are auditable confirmations.

## P6 — Live meeting context and controlled capture

**Goal:** Make meetings strategic without treating AI output as truth.

**Work:** build live agenda/pack, cited Q&A, consent-governed transcript/notes intake,
candidate decisions/actions/positions, corrections, and review queues.

**Exit:** answers are cited and permission-filtered; every candidate is editable/reviewable;
confidential multi-hop graph content has regression coverage; no candidate auto-commits.

## P7 — Decisions, minutes, and memory review

**Goal:** Make every completed meeting a trustworthy institutional record.

**Work:** deliver decision review/detail, citations, positions, supersession, draft/final
minutes versioning, proposal/quarantine review, timeline, filters, and source drill-down.

**Exit:** a founder can reconstruct decision/rationale/stakeholders/evidence/reversal;
published minutes/decisions are immutable versions; research quality and RBAC do not regress.

## P8 — Resolution policy and decision-to-execution bridge

**Goal:** Convert approved decisions into accountable work while respecting legal scope.

**Work:** finalize voting/e-signature policy; create commitments with owners/deadlines/
statuses; add confirmed task/notification adapters with retries/reconciliation; report work
in the next meeting.

**Exit:** execution-required decisions have commitments or a recorded exception; external
delivery is confirmed/idempotent/observable; informal actions, commitments, and resolutions
remain distinct.

## P9 — Product quality gates and operations

**Goal:** Establish production-scale test and operating discipline.

**Work:** make research benchmark regression gates; add model/prompt/ontology review,
metrics/tracing, latency/error monitoring, integration-failure tests, accessibility audit,
and load baselines.

**Exit:** claims have reproducible evidence; model changes require reviewed comparisons;
operations detect provider, access, latency, and delivery failures.

## P10 — Cross-module context and strategic intelligence

**Goal:** Use authorized operating data without ungoverned automation.

**Work:** add finance/CRM/HR/product read adapters with source precedence and timestamps;
provide cited KPI summaries, recommendations, risk/staleness/contradiction signals, aliases,
and abstention.

**Exit:** every result names source/time/scope/authorization; recommendations are measured,
reviewable, and abstain safely; none causes external/permanent action without confirmation.

## P11 — Production readiness

**Goal:** Prove safe operation for confidential board workflows.

**Work:** complete deployment, isolation, alerts, backup/restore, DR, support, incidents,
security/privacy review, penetration tests, accessibility, load tests, and outage exercises.

**Exit:** readiness review approves requirements; restore/incident drills succeed; supported
integrations and legal/jurisdiction limits are published truthfully.

## P12 — Controlled pilot and launch decision

**Goal:** Validate Meridian in real founder workflows before broad release.

**Work:** onboard a defined pilot, record preparation-time baseline, train users, collect
consent, support three board cycles, capture feedback/trust incidents, and review outcomes.

**Exit:** pilot cycles are completed; PRD measures are recorded (preparation and retrieval
time, record completeness, execution continuity, adoption); launch has documented go/no-go,
known limits, and post-launch owners.

## Definition of initial product completion

Meridian reaches initial production scope when an authorized founder can prepare a meeting,
publish a permissioned pack, use cited history during discussion, review source-backed
decisions/minutes, create and track reviewed commitments, retrieve history later, and prove
that no caller can access material outside their authorization. The workflow must be
versioned, auditable, observable, accessible, reproducible, and validated in the pilot.
