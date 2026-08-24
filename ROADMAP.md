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

## Current progress — 2026-08-22

| Track | Completed | Active | Remaining |
|---|---:|---|---:|
| Research engine | **14 / 14** accepted (`R0`–`R13`) | — research track CLOSED 2026-07-18, baseline frozen at `6ed5ed5` | 0 |
| Meridian product | **3 / 13** accepted (`P0`, `P1`, `P2`) | **P3 FROZEN**, exit gate not claimed (CP-F/G/H deferred, #93) · **P4 IN PROGRESS** — source intake merged, versions and meeting assignment not started | **10** (`P3`–`P12`) |

The counts must not be combined into one percentage: the research track validates the
memory engine; the product track makes it a deployable board operating system. P3 gave the
product an authenticated API and an OIDC identity. CI has run the gated suite against real
Postgres and Neo4j on every pull request since #120, but the mechanism gate is not part of
it, and there is still no public deployment, no integration layer, and no pilot.

### P2 checkpoint status

P2 is being delivered one aggregate root per checkpoint, each with its own migration,
domain module, and tests.

| Checkpoint | Aggregate | Migration | Status |
|---|---|---|---|
| CP1 | `Meeting` | `0007_meeting` | ✅ merged (PR #17) |
| CP2 | `AgendaItem` | `0008_agenda_item` | ✅ merged (PR #20) |
| CP3 | `BoardPack` / minutes | `0010_board_pack` | ✅ merged (PR #33) — delivered out of order, exception closed with issue #23 |
| CP4 | `Decision` / `DecisionStance` | `0009_decision` | ✅ merged (PR #22) |
| CP5a | `BoardMember` directory | `0012_board_member` | ✅ merged (PR #42, issue #39) |
| CP5b | membership wiring + `principal` scoping | `0013_principal_rls` | ✅ merged (PR #43, issue #40) |
| CP6 | `Resolution` / `ResolutionVote` | `0014_resolution` | ✅ merged (PR #54) |
| CP7 | `Commitment` / `CommitmentUpdate` | `0015_commitment` | ✅ merged (PR #57) |
| CP8 | `AuditEvent` | `0016_audit_event` | ✅ merged (PR #61) |
| CP9 | notification | — | ⏸️ **deferred to P8** — recorded exception, owner Devguru-codes, issue #62 |
| CP10 | P2 exit gate (no migration) | — | ✅ **PASSED 2026-07-29** — [acceptance record](./docs/reviews/2026-07-29-p2-acceptance.md) |

CP5 was split into **CP5a** (the `BoardMember` directory) and **CP5b** (wiring `membership`
and scoping `principal`) once CP5a's security review showed that clearance was still being
read from the legacy `principal.clearance` column. Detail for CP6–CP10 is in
[docs/proposals/2026-07-27-p2-remaining-checkpoints.md](./docs/proposals/2026-07-27-p2-remaining-checkpoints.md).

**CP3 exception — closed.** CP4 took the `0009` slot that CP3 had reserved, so CP3 shipped
later as `0010`. The chain stayed linear and valid throughout; both checkpoints are merged
and the recorded exception (issue #23) is closed.

**CP9 deferred to P8 — recorded exception (owner: Devguru-codes, issue #62).** Nothing in P2
produces a notification: there is no dispatcher, adapter, scheduler, or user-facing trigger.
Building the table now would put a schema in the frozen chain that no code writes to, designed
against zero real call sites. P8 is where notification *delivery* lives, alongside the retry
state CP7 already models on `commitment`. The proposal's own dependency graph notes that CP9
is the only checkpoint whose removal does not break the chain — CP10 depends on CP8, not CP9.
**Do not close CP9 by adding an empty table.**

**Migration numbers have shifted since the CP5–CP9 proposal was written.** That document
assigned `0011_board_member` through `0015_notification`. `0011` was taken by the P1
control-plane RLS patch (PR #38, issue #32) and `0012`/`0013` by CP5a/CP5b, so the numbers in
the proposal are one to two slots behind. Take the next free slot from
`meridian/migrations/versions/`, not from the proposal.

**Released:** migrations `0011`–`0013` are frozen in tag **`meridian-p1.0.5`** (2026-07-28).
See [docs/reviews/2026-07-28-meridian-p1.0.5-freeze.md](./docs/reviews/2026-07-28-meridian-p1.0.5-freeze.md)
for the verification record and the three limitations carried forward.

### Retrieval core is FROZEN (2026-07-17)

The retrieval core — extraction, verifier, quarantine, planner, grounding/entity linking,
multi-hop traversal, RBAC, approval — is **frozen**. R12 (instrumentation + infrastructure
and benchmark fixes) is merged to `master` (PR #2); it changed **no** core algorithm.

**The rule going forward: a change to the retrieval core requires evidence from evaluation,
not intuition.** A new grounding, linking, abstention, or extraction algorithm is justified
only by a *measured, repeatable* gap in the benchmark, reviewed and recorded in
`docs/findings.md`. The R12 session is the precedent: instrumentation showed the suspected
grounding deficit was partly a benchmark artifact and a partly-fixed infrastructure bug, so
the planned abstention algorithm was **not** built. See `docs/reviews/2026-07-17-r12-
instrumentation.md` (Decision fields open for the reviewer) and the "Future Research" section.

**Before any core change, the current bar is: verify → document → validate.** Stabilise the
evaluation (multi-run stability report), close or characterise the remaining infrastructure
noise (bge-m3 NaN), and validate on messy real-world documents. Only a bottleneck that
survives all three is grounds to unfreeze.

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
- [x] Candidate recall, grounding accuracy, false positives, latency, and downstream traversal effects **measured live (2026-07-17)** — candidate recall 100% on retrieved questions, planner-dominated latency ~20:1, precision fault reduced to a single case. Instrumentation merged (PR #2); reviewer acceptance vs `eval-baseline-v2` pending in `docs/reviews/2026-07-17-r12-instrumentation.md`. **Finding: abstention not justified — core frozen instead of extended.**

## R13 - Research handoff and frozen baseline - ✅ COMPLETE (2026-07-18, owner: Raghav)

**Goal:** Close the research phase with a reproducible contract for product work.

**Work completed:** `docs/research-handoff.md` consolidates reproducible commands, the
named baseline, capability/evidence/limitation matrix, frozen-core exception process, and
the decision rule for P0. The R8–R12 live evaluation ran cleanly on 2026-07-18 (full 21/21
denominator, gated planner adopted); acceptance is recorded in
`docs/reviews/2026-07-18-r13-acceptance.md`. **Accepted baseline commit: `6ed5ed5`.**

**Exit checklist:**

- [x] The handoff lists commands, corpus/evidence references, and limitations for every implemented capability.
- [x] The freeze boundary and exception record are documented.
- [x] R8-R12 live-evaluated and reviewed — clean 21/21 A/B, gated planner accepted (`docs/reviews/2026-07-18-r13-acceptance.md`).
- [x] Baseline accepted and frozen at `6ed5ed5`; to be tagged as the immutable research baseline (new tag — `eval-baseline-v1/v2` are the older R6/R7 baselines).
- [x] Product checkpoint P0 is now **authorized**.

---

# Future Research — open questions, not planned features

These are recorded as **questions the evidence has not yet answered**, deliberately not as
committed checkpoints. None authorises a core change; each names what would have to be
*measured* first. This section exists so that "we should improve grounding" never re-enters
the roadmap as an assumption — it must arrive as a reproduced gap.

- **Does any grounding weakness survive a clean benchmark?** The 2026-07-17 run showed the
  apparent grounding deficit was partly benchmark design and partly infrastructure noise, and
  that on a densely-linked graph *seed-grounding accuracy does not track answer correctness*
  (a question can seed the "wrong" of two linked decisions and still answer correctly via
  traversal). Open question: after a fully clean rerun, is there a repeatable grounding gap at
  all — and if so, is it a linker problem or a metric problem? No abstention or linker work is
  justified until this is answered with evidence.

- **What is the root cause of the intermittent bge-m3 NaN?** It persists at a low rate even
  with the model resident (`keep_alive`) and is not reproducible in isolation (0/27 in
  controlled probing), so it is not cold-reload or GPU eviction (the chat model is cloud-
  hosted and never touches local VRAM). Open question: is it a bge-m3/llama.cpp compute fault,
  an Ollama concurrency issue, or input/state-specific? Until understood, it is *contained*
  (excluded from grounding metrics, never mis-scored) but not *closed*. No further workaround
  without a demonstrated cause.

- **Coreference (M16) is an unbuilt capability, not a bug.** "that proposal" / "the prior
  motion" fail because there is no reference-resolution stage. Open question: does chunk
  context, graph context, or a reviewed coreference stage close a *measured* gap — and is the
  gap large enough on realistic input to justify a new stage? Belongs behind the real-world
  validation set, not ahead of it.

- **Conflict synthesis (M15) is a presentation gap, not a retrieval one.** Both conflicting
  sources are retrieved with provenance (recall 100%); the answer layer does not always
  present the disagreement. Open question: is this an answer-prompt refinement (cheap, no core
  change) or does it need structured conflict signalling?

- **Does the frozen core generalise off its own corpus?** The benchmark shares our author and
  our tidiness. Open question: on messy real-world documents (see
  `docs/proposals/2026-07-17-real-world-validation-corpus.md`) do quarantine rate, grounding,
  and abstention degrade gracefully? A held-out set that *fails to* lower the numbers is strong
  generalisation evidence; whichever capability breaks first is the next evidence-backed reason
  to unfreeze.

- **Identity disambiguation under colliding surface forms.** The current alias fixture tests
  one cluster vs one outsider. A harder draft (two clusters sharing tokens: "Raj"/"Rajesh",
  "R. Malhotra"/"R. Kumar" — `docs/proposals/2026-07-17-meeting14-identity-draft.md`) is
  proposed for review. Open question: does candidate grounding + `ALIAS_OF` keep two people
  distinct when their forms nearly collide, without a linker change?

---

# Track B — Meridian Board Operating System

This track begins only after R13. It turns Callosum’s verified memory engine into the
founder-facing board workflow specified in `PRD.md`.

## P0 — Product contract and delivery controls — ✅ ACCEPTED

**Goal:** Make the PRD executable.

**Work:** assign product, engineering, security, and pilot owners; create requirements
traceability; set decision-log/change-control rules; lock pilot segment and V1 scope.

**Exit:** every V1 requirement has owner, priority, dependency, and testable evidence;
human-control/evidence/RBAC invariants are signed off; no static prototype is called built.

## P1 — Production security, tenancy, and governance design — ✅ ACCEPTED

Shipped and re-frozen across `meridian-p1` → `p1.0.1` (conflict-scan tenant scope) →
`p1.0.2` (Neo4j query gateway, defect class D-001) → `p1.0.3` (deterministic mechanism
eval gate) → `p1.0.4` (workspace-scoped `entity_conflict` unique key). The exit criterion
"unauthorized content is blocked in Cypher" was initially unmet — see the F2 defect in
`docs/proposals/2026-07-20-p2-measurement-neo4j-tenant-surface.md` — and was closed by the
`p1.0.1` patch before P1 was accepted.

**Goal:** Define access, retention, and processing rules before real board data enters a
web application.

**Work:** specify tenancy, identity, role/object policy, invitation lifecycle, audit,
retention/deletion, consent, encryption, secrets, backups, incident response, processors,
and residency; evolve clearance-only retrieval to reviewed object-level policy.

**Exit:** security approves threat/data-flow models and role matrix; unauthorized content is
blocked in SQL, Cypher, quotes, chunks, logs, APIs, and UI; transcript policy is approved.

## P2 — Durable product domain and migrations — ✅ ACCEPTED

Checkpoint-by-checkpoint status is tracked in the P2 table under
[Current progress](#p2-checkpoint-status).

**Goal:** Model the board workflow absent from Callosum.

**Work:** migrate workspace, member, board, meeting, agenda/pack/minutes versions,
decision, resolution, commitment, notification, and audit objects; define lifecycle states,
publication/version semantics, ownership, and retries.

**Exit:** migration/recovery plan is tested; invalid transitions and cross-workspace access
are rejected; superseded/published records preserve immutable history.

## P3 — Authenticated API and accessible application shell — 🧊 FROZEN (feature-complete, exit gate not claimed)

**Frozen 2026-08-01 at `caf650d`** — [freeze record](./docs/reviews/2026-08-01-p3-freeze.md).
Feature-complete through CP-E. The phase is **not** marked accepted: of its three exit
criteria, one is met, one is partial and one is not met, because CP-F/CP-G/CP-H were
deferred by recorded exception (#93). Counting it as accepted would make this table say
something the evidence does not support.

### Checkpoint status (2026-08-01)

Design in [docs/proposals/2026-07-29-p3-implementation-roadmap.md](./docs/proposals/2026-07-29-p3-implementation-roadmap.md);
decisions in ADR-009 – ADR-014.

| CP | Scope | Status |
|---|---|---|
| §5 | work needing no decision | ✅ tenancy guard · id lookup · error taxonomy · `decisions.ts` fix · `/commitments` |
| CP-A | identity + session | ✅ `principal_identity` · subject resolution · OIDC/Keycloak · workspace selection · OpenAPI guard |
| CP-B | first vertical slice | ✅ `/api/resolutions` + real client, mock deleted |
| CP-C | remaining mechanical reads | ✅ **7 / 7** — `board_members` `agenda` `meetings` `packs` `minutes` `decisions` `commitments`. *Corrected 2026-08-01: the API landed for all seven in P3, but the `decisions` and `commitments` **client** swaps were missed and only completed during the demo build-out. The checkpoint was reported complete when it was 5/7 on the frontend.* |
| CP-D | writes + 409 concurrency | ✅ **complete** — D1/D2 all eight aggregates; D3 client write path with actionable 409 handling |
| CP-E | the four orphan mocks | ✅ **complete** — `documents` live; `insights` audited tile by tile; `graph` + `assistant` deferred to P6 (recorded exception, issue #100) |
| CP-F | states, rate limits, observability | ⬜ |
| CP-G | accessibility | ⬜ |
| CP-H | P3 exit gate | ⬜ |

**Six of the seven mock swaps found a contract defect**: nothing enforced the TS↔Python
correspondence at all; `include_inactive` was invented *and* lossy; three phantom
`Meeting` fields (`agenda`, `objectives`, `sensitivity`); a nullable scheduling window
declared as required; `clearance` accepted as a *client* argument on packs; and
`board_member_id` declared on `DecisionStance` but dropped by `_row_to_stance`, so a
stance resolved to a director arrived looking unresolved. Each is now pinned by a
cross-language test that reads the TypeScript and compares it to the Python.

**`commitments` was the exception, and the reason generalises.** It is the only mock
written *after* its domain shipped, against the real contract rather than ahead of it —
fields, statuses, transitions and the `NULLS LAST` sort all matched. Every defect above
came from a mock authored before the Python existed. Write the domain first and the
swap is a change of transport; write the mock first and it is a negotiation.

**Open decisions:** D7 (who may read the audit trail) gates only the `audit` endpoint.
The CP-E orphans need a call each — `graph` and `assistant` recommended for deferral to
P6, `insights` for a tile-by-tile derive-or-delete audit.


**Goal:** Provide a secure founder-facing interface over approved core functions.

**Work:** select/document stack; build sign-in, workspace selection, role-aware navigation,
dashboard, directory, withheld/error/loading states, secure API contracts, rate limits, and
observability.

**Exit:** users access only authorized workspaces; UI distinguishes draft/approved/withheld/
failed states; primary flows pass keyboard and accessibility smoke checks.

## P4 — Board workspace, members, and source intake — 🟩 IN PROGRESS

Source intake merged 2026-08-22 (PR #128); versions built 2026-08-23. **Not accepted:** the
exit gate has not been attempted, and `rules.md` §4 is explicit that only an exit gate advances the accepted count,
so the product track stays at 3 of 13. Checkpoint detail in [phase.md](./phase.md#product-p4--board-workspace-members-and-source-intake--in-progress).

| Work item | State |
|---|---|
| Members | ✅ shipped early as P2 CP5a / CP5b |
| Document intake / import · metadata / sensitivity · duplicates · quarantine state | ✅ merged (#128) |
| Versions | ✅ built 2026-08-23 (`0024_document_version`, ADR-017) |
| Workspace / meeting assignment | ⬜ not started |
| Exit gate | ⬜ not attempted |

**Recorded gap — CLOSED.** Intake applied no sensitivity ceiling: a clearance-1 principal
could file a sensitivity-3 document. Raised in #128's review, decided in #143 and shipped in
#144 (`SensitivityAboveClearanceError`, 403, a refusal rather than a clamp). Kept here as the
record of a gap that was decided rather than patched in quietly.

**Versions, 2026-08-23 — built, and it does not move the count.** A document is corrected by
supersession, never by mutation (ADR-017). The load-bearing rule is that a revision may
**never lower** sensitivity: a corrected confidential document filed as public would
republish its lineage a clearance rung down, and content-hash dedup cannot catch it because
a correction differs by construction. Withheld revisions in a chain are disclosed as a
**count**, never a title, and `current_id` is null rather than promoting a superseded
revision. `rules.md` §4 is explicit that only an exit gate advances the accepted count, so
the product track stays at **3 of 13**.

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
