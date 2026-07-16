# Meridian Path to Completion

## Operating rule

This is a sequential delivery plan. Start only the next checkpoint after the current checkpoint satisfies every exit criterion, its evidence has been reviewed, and unresolved risks are explicitly accepted or moved into a named backlog item. “Code exists” is never sufficient evidence of completion.

The route builds the full Meridian Board Operating System. Callosum is the trusted institutional-memory foundation already partly implemented in this repository; it is not treated as proof that the full board product exists.

## Global completion standards

Every checkpoint must produce:

- A short decision record: scope, owner, evidence, deferred items, and known limitations.
- Tests appropriate to the risk, including negative/security cases where access or automation changes.
- Updated product/technical documentation and an explicit implementation-status entry.
- A reviewed `git diff`, passing relevant checks, and a runnable handoff command.
- No unapproved weakening of evidence verification, human review, RBAC, provenance, or auditability.

## Checkpoint 0 — Product contract and delivery controls

**Purpose:** Establish the source of truth so implementation follows one coherent product rather than a prototype, old draft, or code comment in isolation.

**Work:**

- Approve `PRD.md` as the working product contract and keep the original Meridian research as contextual evidence only.
- Define product owner, engineering owner, security/review owner, pilot owner, decision-log format, and change-control rule.
- Create a requirements traceability matrix from PRD requirement IDs to design, code, tests, and acceptance evidence.
- Record the distinction between implemented Callosum foundation capabilities and planned Meridian workflows.

**Exit checklist:**

- [ ] Every V1 requirement has an owner, priority, dependency, and testable acceptance condition.
- [ ] Product, security, and engineering sign off on human-control and source-provenance invariants.
- [ ] The pilot segment is defined: founder-led startups from pre-seed to Series B.
- [ ] No feature is marked “built” based only on the original static prototype.

## Checkpoint 1 — Make the Callosum foundation reproducible

**Purpose:** Turn the existing CLI proof-of-foundation into a dependable, repeatable development baseline.

**Work:**

- Standardize local environment setup, Python 3.12 installation, configuration validation, and service startup.
- Run and repair the deterministic test suite; record required live-provider setup separately.
- Reproduce seeded hybrid-vs-vector evaluation and capture baseline results, model, prompt, ontology, corpus revision, and date.
- Validate the normal ingestion path: dedupe, chunk offsets, embedding dimensions, proposal queue, approval, quarantine, graph bridge, and grounded query.
- Create a machine-readable implementation-status matrix for current modules and known gaps.

**Exit checklist:**

- [ ] A new developer can run `doctor`, initialize stores, run tests, and reproduce the evaluation from documented commands.
- [ ] Fast tests pass under supported Python 3.12.
- [ ] The evaluator has a declared gold graph and separate extraction-quality reporting.
- [ ] The present limitations—exact name resolution, low grounding precision, clearance-only retrieval policy, and small corpus—are documented with evidence.

## Checkpoint 2 — Security, tenancy, and data-governance design

**Purpose:** Define the security model before introducing a web application or importing real board material.

**Work:**

- Design workspace tenancy, identity integration, role/permission policies, object-level access, invitation lifecycle, and audit-event model.
- Define source, transcript, recording, derived-data, and audit-log retention/deletion rules.
- Threat-model document ingestion, provider calls, vector search, graph traversal, citations, notifications, external integrations, and administrator actions.
- Define the production secret-management, encryption, backup/restore, incident response, and processor/data-residency policy.
- Specify the per-object ACL retrieval predicate and test it against the current clearance-only implementation.

**Exit checklist:**

- [ ] Security owner approves the threat model and data-flow diagram.
- [ ] Each user-visible role has an explicit allow/deny matrix.
- [ ] “No unauthorized data enters context” is tested for SQL, Cypher, graph quotes, graph-resolved chunks, logs, and UI/API responses.
- [ ] Retention and consent policy is approved before transcript/recording ingestion is enabled.

## Checkpoint 3 — Durable product domain and migration strategy

**Purpose:** Add the product objects that Callosum alone does not model.

**Work:**

- Specify and migrate workspace, member, board, meeting, agenda version/item, board-pack version/item, minutes version, decision, resolution, commitment, notification, and audit objects.
- Map Callosum document/chunk/entity/proposal records to workspace and meeting ownership without breaking the existing provenance bridge.
- Define lifecycle state machines and allowed transitions for meeting, pack, decision, minutes, resolution, and commitment objects.
- Implement append-only/versioned publication semantics and transaction/retry expectations.

**Exit checklist:**

- [ ] Migrations are reversible or have an approved forward-only/backfill plan and restore test.
- [ ] Each object has workspace ownership, authorization policy, audit behavior, and retention behavior.
- [ ] Decision supersession and published-artifact versioning preserve historical records.
- [ ] API/domain tests reject invalid state transitions and cross-workspace access.

## Checkpoint 4 — Product API and founder-facing application shell

**Purpose:** Make the foundation usable through an authenticated application, not a terminal-only demo.

**Work:**

- Select and document the web/API stack, API conventions, error model, session/auth flow, and deployment topology.
- Build authenticated workspace selection, role-aware navigation, board directory, dashboard, audit visibility, and empty/error/loading states.
- Expose the approved Callosum functions through secure APIs without importing UI concerns into frozen core modules.
- Add API contracts, observability, rate limits, structured errors, and accessible UI primitives.

**Exit checklist:**

- [ ] Users can sign in, enter only authorized workspaces, and see an auditable identity/role context.
- [ ] No API can access another workspace by identifier manipulation.
- [ ] UI distinguishes unavailable, withheld, draft, approved, and failed states.
- [ ] Accessibility smoke tests cover keyboard navigation and core route labeling.

## Checkpoint 5 — Board workspace, members, and document intake

**Purpose:** Establish the single source of truth for board material and people.

**Work:**

- Implement workspace creation/configuration, board-member directory, invite/revoke flows, role policy, and document sensitivity controls.
- Build document upload/import, metadata review, source version display, duplicate handling, processing state, and failure/quarantine presentation.
- Assign documents to workspace and optional meetings/board packs; surface exact provenance where extraction produces proposals.
- Add permission tests for founders, directors, observers, executives, and investors.

**Exit checklist:**

- [ ] An authorized administrator can add/remove board participants and audit each change.
- [ ] An uploaded document’s status is visible from intake through indexing/proposal review.
- [ ] A low-clearance user cannot see a restricted document, its title, text, extracted quote, graph fact, or retrieval hint.
- [ ] Re-upload/version behavior is explicit and does not silently duplicate institutional facts.

## Checkpoint 6 — Meeting, agenda, and board-pack lifecycle

**Purpose:** Deliver the first practical founder workflow: prepare and publish a coherent pre-read.

**Work:**

- Implement meeting creation, attendee selection, meeting lifecycle, sensitivity, objectives, and agenda editing/timeboxing.
- Generate a reviewable agenda draft from unresolved actions, prior decisions, and selected operating context; show evidence/reason for every suggestion.
- Build board-pack assembly, ordering, versioning, completeness review, stale-data checks, approval, publish, and read-only attendee view.
- Add provider adapters for calendar/email as drafted, previewed, explicitly confirmed actions only.

**Exit checklist:**

- [ ] A founder can take a meeting from draft to published pre-read with an immutable published version.
- [ ] The pack review identifies missing required items, unresolved commitments, and stale sources with actionable evidence.
- [ ] Publishing is authorized, auditable, permission-aware, and never sends messages without confirmation.
- [ ] A director can read only the published items allowed by their policy.

## Checkpoint 7 — Live meeting context and controlled capture

**Purpose:** Support strategic discussion without letting AI create unreviewed institutional facts.

**Work:**

- Build the live meeting view for agenda, pack context, approved historical Q&A, note-taking, and candidate capture.
- Connect transcript/notes ingestion subject to consent/retention policy; support graceful manual-note fallback.
- Present candidate decisions, relationships, actions, positions, and summaries with source spans, confidence, and explicit uncertainty.
- Enable manual correction and human review queues; prohibit automatic inference from silence.

**Exit checklist:**

- [ ] A live question receives only permission-filtered, cited context and displays withheld-source count when needed.
- [ ] Every candidate fact can be edited, approved, rejected, or returned; no candidate is silently committed.
- [ ] The system proves that a confidential graph edge/quote cannot leak in a multi-hop answer.
- [ ] Manual and AI-originated captures remain distinguishable in audit history.

## Checkpoint 8 — Decision, minutes, and memory review

**Purpose:** Make each meeting create a trustworthy, navigable institutional record.

**Work:**

- Deliver decision review/detail screens with rationale, evidence, participants, positions, outcome, owner, status, and supersession chain.
- Deliver editable draft minutes, reviewed source citations, finalization/versioning, and secure publication.
- Surface proposal/quarantine queues and explain failure reasons in reviewer language.
- Deliver the founder memory interface: decision timeline, filters, cited natural-language search, and source drill-down.

**Exit checklist:**

- [ ] A founder can reconstruct what was decided, why, by whom, from which source, and what replaced it later.
- [ ] Final minutes and decision records are versioned and immutable; corrections create a new version with reason.
- [ ] All claimed graph facts shown in UI are approved and source-backed.
- [ ] Retrieval quality, grounding, and RBAC suites meet or improve the recorded baseline without hiding regressions.

## Checkpoint 9 — Resolution policy and decision-to-execution bridge

**Purpose:** Connect governed decisions to owned work without conflating draft notes, decisions, and legal resolutions.

**Work:**

- Define corporate-policy and jurisdiction boundaries for voting, written consents, and signatures; implement only approved scope.
- Implement commitment creation, owner/team/deadline/status assignment, evidence updates, and decision linkage.
- Implement reviewed task/notification adapters with idempotency, delivery status, retry, reconciliation, and opt-out/override behavior.
- Add next-meeting reporting for overdue, blocked, completed, and materially changed commitments.

**Exit checklist:**

- [ ] Every execution-required approved decision has explicit commitments or an auditable no-execution rationale.
- [ ] External task/notification delivery is user-confirmed, observable, retriable, and never marked successful without evidence.
- [ ] The product clearly separates informal action items, approved commitments, and legally formal resolutions.
- [ ] The next pack correctly reflects execution status and links it to the originating decision.

## Checkpoint 10 — Evaluation corpus, quality gates, and model operations

**Purpose:** Prevent the product from appearing trustworthy only on one curated transcript.

**Work:**

- Expand the corpus deliberately: multiple meetings, varied document types, reversals, aliases, conflicting evidence, vague references, long/messy text, and confidentiality cases.
- Extend gold questions and expected facts by strata, including negative/abstention and adversarial permission cases.
- Establish model/prompt/ontology comparison reports, threshold policy, regression triage, and change-approval process.
- Implement production monitoring for extraction failures, citation/retrieval quality proxies, grounding, provider errors, permission denials, latency, and integration failure.

**Exit checklist:**

- [ ] Every capability claim has a source dataset and measured acceptance metric.
- [ ] Hybrid/vector comparison uses shared plans and declared gold facts; extraction is measured separately.
- [ ] A model/prompt/ontology change cannot ship without a baseline comparison and reviewer decision.
- [ ] Security regression tests include document, graph, query, citation, and UI/API paths.

## Checkpoint 11 — Cross-module context and strategic intelligence

**Purpose:** Use accumulated trusted data to improve board quality without turning inference into ungoverned automation.

**Work:**

- Add authorized read adapters for selected finance, CRM, HR, product, and operating-data systems with source precedence and refresh visibility.
- Provide evidence-grounded KPI summaries, agenda recommendations, stale/at-risk decision signals, and contradiction flags.
- Implement candidate retrieval/alias strategy that scales beyond a tiny entity vocabulary and supports abstention.
- Make every recommendation explainable, editable, and reviewable before it affects a pack, task, message, or record.

**Exit checklist:**

- [ ] Cross-module answers cite source system, timestamp, scope, and authorization basis.
- [ ] Recommendations are measured against a baseline and have a documented abstention/degraded path.
- [ ] Grounding precision and recall are measured on realistic aliases and no-referent queries.
- [ ] No recommendation performs an external or permanent action without explicit user approval.

## Checkpoint 12 — Production readiness, pilot, and controlled launch

**Purpose:** Verify that Meridian works for real board workflows under real operational constraints.

**Work:**

- Complete deployment, tenancy isolation, monitoring, alerting, backups, restore drills, disaster recovery, support operations, and incident response.
- Conduct privacy/security review, penetration testing, accessibility audit, load/performance test, and integration failure exercises.
- Onboard a small defined pilot with baseline measurement, training, consent collection, feedback loop, and support escalation path.
- Review product outcomes, trust metrics, adoption, security events, and roadmap assumptions before expanding access.

**Exit checklist:**

- [ ] Production readiness review approves all non-functional and security requirements.
- [ ] Backup restore and incident runbooks are exercised successfully.
- [ ] Pilot users complete at least three board-workflow cycles or a documented equivalent and outcome metrics are measured.
- [ ] Launch decision records evidence, known limitations, supported integrations/jurisdictions, and post-launch owners.

## Definition of complete

Meridian is complete for its initial production scope only when a permitted founder can securely prepare a meeting, publish the correct pack, use cited historical context during the meeting, review source-backed decisions and minutes, assign and track resulting commitments, retrieve the complete decision history later, and demonstrate that no user can retrieve information outside their authorization. All of this must be reproducible, observable, auditable, accessible, and measured against the quality/security gates above.
