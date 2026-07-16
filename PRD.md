# Meridian Board Operating System — Product Requirements Document

**Status:** Living product specification
**Product:** Meridian Board Operating System, powered by the Callosum institutional-memory engine
**Primary audience:** Product, design, engineering, security, and research teams
**Product boundary:** The complete founder-facing board-workflow product. Callosum is the verified knowledge, retrieval, and provenance foundation—not the whole product.

## 1. Executive summary

Meridian helps early-stage startups run board operations as one continuous, secure workflow: prepare the meeting, conduct the discussion, record governed decisions, turn them into accountable work, and retrieve their history later. Its core promise is that a founder should never have to rebuild context from email threads, folders, decks, and memory to answer: *“Why did we reject this?”*

The initial target is a founder-led company from pre-seed through Series B. These teams normally manage board work across Google Drive, email, Slack, Notion, Zoom, and DocuSign. Those tools can store files or send messages, but they do not preserve the relationship between a discussion, its evidence, the formal decision, dissent, approval, owner, execution status, and later reversal.

Meridian’s differentiator is a governed institutional-memory layer, implemented by Callosum. It joins source documents and semantic retrieval with a verified knowledge graph. Every AI-proposed graph relationship must have a machine-checked source quote; no model output mutates institutional memory until an authorized human approves it; and access control excludes confidential content before retrieval. The workflow application turns that foundation into useful board preparation, meeting intelligence, decision management, and execution tracking.

## 2. Problem, opportunity, and product thesis

### Problem statement

Board management is not fundamentally a scheduling or note-taking problem. It is a **workflow-continuity problem**. As a startup grows, information becomes fragmented, institutional knowledge decays, decisions fail to reach execution, and founders repeat administrative reconstruction before every meeting.

The recurring founder problems are:

- Board packs, minutes, financials, approvals, and discussions are scattered and version-confused.
- Board preparation requires manual collection of KPIs, status, past decisions, and unresolved action items.
- Directors receive late or incomplete pre-reads; meetings become status updates rather than strategic discussion.
- Decisions, votes, rationale, dissent, and ownership are not reliably captured together.
- Follow-ups are copied into unrelated tools, then forgotten or difficult to report on.
- Confidential material is shared through tools with inconsistent permissions and incomplete audit trails.
- Months later, no one can reliably reconstruct what was decided, why, who supported or opposed it, what evidence was considered, or whether the decision was superseded.

### Opportunity

The market has a gap between low-cost generic tools that require manual coordination and enterprise board portals that are expensive, complex, and designed for mature governance. Meridian must be startup-first: self-serve, understandable, integrated with operating data, and opinionated about sound governance without becoming a public-company compliance suite.

### Product thesis

Meridian is not another document portal. It is the startup’s operating memory: a system where board knowledge remains attributable, permissioned, current, and connected to execution.

## 3. Research context and product implications

This specification synthesizes the original Meridian discovery work: market/user research, product/competition/GTM research, product thesis, pain-point matrix, high-value use cases, prioritization, journey, build-vs-buy analysis, original MVP PRD, prototype, and institutional-memory concept. Those artifacts establish context; this document translates it into buildable requirements for the actual Callosum repository.

| Research finding | Product implication |
|---|---|
| Founders commonly spend 15–20 hours preparing a board meeting. | Preparation must assemble prior decisions, unresolved work, and current metrics into an editable draft—not merely store files. |
| Startups rely on Drive, email, Slack, Zoom, Notion, and DocuSign. | Meridian must provide a coherent board workflow while integrating mature services instead of rebuilding them. |
| Existing board portals are either enterprise-heavy or partial point solutions. | The UX must keep core workflows short, founder-oriented, self-serve, and transparent in pricing/complexity. |
| The highest-value unmet need is institutional memory. | Provenance, retrieval, decision history, and secure access are product-critical, not supporting infrastructure. |
| Automation is valuable only when a human can review consequential outputs. | AI may draft, propose, summarize, and route; it must not autonomously approve, send, sign, vote, or mutate memory. |
| Board work spans meeting preparation, live discussion, and follow-up. | The product must represent the lifecycle as a single connected workflow, not independent screens. |

## 4. Goals and non-goals

### Goals

1. Give every board meeting one authoritative workspace for agenda, board pack, source material, decisions, minutes, approvals, and actions.
2. Reduce founder preparation effort while improving the quality and timeliness of pre-reads.
3. Preserve decision history with source-backed rationale, stakeholders, ownership, and change over time.
4. Convert approved board decisions into accountable, visible execution.
5. Let authorized users retrieve board context in natural language with citations and clear withholding behavior.
6. Make permissions, auditability, review, and data provenance trustworthy enough for confidential startup board material.

### Non-goals

- Replacing Carta or another cap-table/equity management product.
- Replacing a general project-management product, CRM, document-management system, or video-conference provider.
- Public-company governance, SOX workflows, committee administration, or jurisdiction-specific legal advice in the initial product.
- Fully autonomous AI actions, including formal approvals, e-signatures, task creation in external systems, or sending communications without explicit user confirmation.
- Claiming legal validity for electronic resolutions until jurisdiction, corporate documents, and e-signature integration requirements are implemented and reviewed.
- Building a generic chatbot detached from board evidence and permissions.

## 5. Users, roles, and authorization model

### Primary users

| Persona | Primary job | Required outcome |
|---|---|---|
| Founder / CEO | Run the board process and make strategic decisions executable. | Prepare quickly, answer confidently, approve durable records, and track outcomes. |
| Chief of Staff / board administrator | Coordinate the mechanics and records of meetings. | Keep materials, agenda, minutes, approvals, and follow-ups complete and timely. |
| Executive owner | Supply operating context and execute assigned commitments. | Understand the decision, evidence, scope, owner, deadline, and status. |

### Secondary users

| Persona | Primary job | Required outcome |
|---|---|---|
| Director / investor | Prepare for and participate in governance. | Read the correct pack, contribute to decisions, and retrieve permitted historical context. |
| Observer / adviser | Supply perspective without formal voting authority. | Access only the meetings and documents explicitly permitted. |
| Legal / finance administrator | Maintain formal records where required. | Retrieve accurate, auditable minutes, resolutions, and supporting material. |

### Roles and access principles

- Every workspace member has a role, organization affiliation where relevant, and sensitivity clearance. The initial clearance ladder is public, investor, internal, confidential, and restricted.
- Access is least-privilege and is checked before content retrieval, ranking, or prompt construction. A response may disclose that sources were withheld, but never their content, titles, graph facts, quotes, or existence beyond the count.
- Meeting-, document-, and object-level policy must be supported by the product design. The current Callosum implementation enforces clearance filtering; per-object ACL grants are not yet active in retrieval and must not be presented as complete.
- Directors, observers, and investors are distinct roles. Voting authority, meeting access, decision review authority, and document permissions are configurable policies, not inferred from text.

## 6. End-to-end experience

```mermaid
flowchart LR
  A[Plan meeting] --> B[Build agenda and board pack]
  B --> C[Review and publish pre-read]
  C --> D[Run meeting with contextual assistance]
  D --> E[Review decisions, minutes, and evidence]
  E --> F[Approve resolution and create execution commitments]
  F --> G[Track work and report progress]
  G --> H[Retrieve history for the next decision]
  H --> B
```

### Core jobs to be done

1. **Prepare:** “When I have a board meeting coming up, help me assemble a complete, current board pack so I can spend my time on strategy instead of chasing information.”
2. **Conduct:** “When a director asks about a past issue, give me an attributable answer from material they are allowed to see.”
3. **Record:** “When the board reaches a decision, capture its outcome, rationale, dissent, evidence, owner, and formal status without relying on memory.”
4. **Execute:** “When a decision produces work, route the commitment to the right owner and show whether it is progressing before the next meeting.”
5. **Recall:** “When I need historical context, show what happened, why, and what changed, with sources I can verify.”

## 7. Scope and release strategy

The roadmap is intentionally sequential. A later release cannot compensate for an untrustworthy record or incomplete workflow below it.

| Release | Outcome | Included capabilities |
|---|---|---|
| Foundation / Callosum | Trusted organizational-memory platform. | Secure document ingestion, verified extraction, approval queue, hybrid retrieval, evaluation, audit trail. |
| V1 — Board workflow | A founder can prepare, run, review, and preserve a board meeting in Meridian. | Board workspace, member access, meetings, agenda, pack assembly/review, live context, decision/minutes review, institutional-memory UI. |
| V2 — Decision execution | An approved decision has accountable, observable downstream work. | Resolution workflow, action lifecycle, reminders, external task/notification integration, progress reporting. |
| V3 — Strategic intelligence | Historical and operating data support proactive board preparation and analysis. | Cross-module context, knowledge search at scale, risk detection, recommendations, controlled automation. |

## 8. Functional requirements

Requirements use `FR-<area>-<number>`. “Must” is release-gating; “should” is targeted but may be explicitly deferred with product approval.

### A. Institutional-memory foundation (existing Callosum scope)

| ID | Requirement | Acceptance condition |
|---|---|---|
| FR-MEM-01 | The system must ingest TXT, Markdown, VTT, PDF, and DOCX sources, normalize text, hash content, and reject duplicate content idempotently. | Re-ingesting identical content creates no duplicate document, chunks, graph nodes, or proposals. |
| FR-MEM-02 | The system must retain raw source text, document metadata, chunk text, and exact character offsets. | For every chunk, slicing raw text at stored offsets equals the stored chunk exactly. |
| FR-MEM-03 | The system must create 1024-dimension embeddings and store them with chunks. | A mismatched embedding dimension fails before persistence; provider switches trigger corpus re-embedding. |
| FR-MEM-04 | AI extraction must return typed entities and relationships under a versioned ontology and prompt. | Every proposed relationship includes source, relation, target, quote, confidence, provider/model, prompt version, and ontology version. |
| FR-MEM-05 | The system must verify every relationship quote against its source before it can be proposed for approval. | Empty, paraphrased, stitched, self-referential, or dangling relationships are quarantined with a typed reason. |
| FR-MEM-06 | A model must never write a production graph node or edge directly. | The only production commit path reads a pending human-reviewed proposal; deterministic evaluation seeding is separately labelled and isolated. |
| FR-MEM-07 | The system must support semantic vector retrieval and bounded graph traversal connected by shared chunk UUIDs. | A graph fact can recover the readable source chunk; a vector hit can reach its linked entities. |
| FR-MEM-08 | All retrieval must enforce permission policy in the source query. | Tests prove inaccessible chunks, quotes, and multi-hop paths never enter the result context. |
| FR-MEM-09 | Every query must produce a retrievable audit record containing principal, plan, retrieved IDs, denied count, answer, and latency. | Authorized auditors can inspect the log without exposing content beyond their access. |

### B. Board workspace and membership (V1)

| ID | Requirement | Acceptance condition |
|---|---|---|
| FR-WS-01 | A founder or administrator can create a company workspace and define default sensitivity policy. | New meetings and documents inherit a visible default that can be tightened by an authorized user. |
| FR-WS-02 | An authorized administrator can add, remove, or change members as director, observer, executive, administrator, or adviser. | Role changes are audited and take effect for subsequent access checks. |
| FR-WS-03 | The product must provide a board member directory with name, organization, role, contact method, voting status, and active/inactive state. | The directory is usable to populate meetings, notifications, and decision review routing. |
| FR-WS-04 | The product must present board material by meeting and decision, not only by file hierarchy. | A user can navigate from a meeting to its pack, minutes, decisions, actions, and supporting sources. |

### C. Meeting planning, agenda, and board pack (V1)

| ID | Requirement | Acceptance condition |
|---|---|---|
| FR-PLAN-01 | An administrator can create a meeting with date/time, location or conference link, attendees, sensitivity, objectives, and status. | The meeting moves through draft, scheduled, in-progress, review, completed, and archived states with an audit trail. |
| FR-PLAN-02 | Meridian must draft an agenda from unresolved actions, pending decisions, prior meeting follow-ups, and selected operating context. | The draft shows each recommendation’s source/reason and remains editable before publication. |
| FR-PLAN-03 | An administrator can order, timebox, assign presenters for, and remove agenda items. | Publishing freezes a versioned agenda snapshot while preserving later revisions as new versions. |
| FR-PLAN-04 | Users can attach or ingest documents into a board pack and assign each to a meeting and sensitivity. | The workspace shows version, author/uploader, status, access policy, and pack position for every item. |
| FR-PLAN-05 | Meridian must run a board-pack review that identifies missing required sections, stale sources, unresolved previous actions, and undefined decision requests. | Findings cite the exact missing/stale condition; the user can dismiss or resolve each finding with an audit record. |
| FR-PLAN-06 | An authorized user can publish a read-only pre-read package to eligible attendees. | Publish records recipient eligibility and time; republishing creates a new immutable pack version. |
| FR-PLAN-07 | The system should integrate calendar and email providers to create invitations and reminders only after user preview and explicit send confirmation. | No invite or email is sent from an AI suggestion without confirmation. |

### D. Live meeting intelligence and capture (V1)

| ID | Requirement | Acceptance condition |
|---|---|---|
| FR-LIVE-01 | A meeting view must surface the current agenda, relevant pack material, unresolved actions, and draft capture panel. | A presenter can navigate without opening separate file tools. |
| FR-LIVE-02 | An authorized participant can ask an evidence-grounded question across permitted historical board content. | The answer includes source citations, distinguishable graph facts, and a withheld-source notice when relevant. |
| FR-LIVE-03 | Meridian may generate draft summaries, candidate decisions, candidate actions, and notable dissent from transcript or notes. | Every draft identifies itself as AI-generated, links its supporting source span, and is editable. |
| FR-LIVE-04 | A participant can manually create or correct a decision, action, attendee record, or meeting note. | Manual edits retain author, timestamp, reason, and linkage to source material when one exists. |
| FR-LIVE-05 | The system must never infer a formal vote, approval, owner, deadline, or participant stance from silence. | The review UI requires an explicit human confirmation for each consequential field. |

### E. Decision, minutes, and institutional-memory review (V1)

| ID | Requirement | Acceptance condition |
|---|---|---|
| FR-DEC-01 | A decision record must hold title, status, topic, meeting, rationale, stakeholders, evidence, requested approval, owner, and effective date where known. | A reviewer can see all required unknown fields as explicitly unknown rather than fabricated. |
| FR-DEC-02 | Decision status must support proposed, approved, rejected, deferred, superseded, and withdrawn/cancelled policy where applicable. | A superseding decision retains a navigable link to the earlier decision; history is never destructively overwritten. |
| FR-DEC-03 | The product must separate support, opposition, proposal, formal approval, request, ownership, attendance, and evidence. | The UI and data contract use the versioned ontology rather than collapsing all relationships into notes. |
| FR-DEC-04 | Reviewers can approve, reject, or return AI proposals individually or in controlled batches. | Each action records reviewer, time, disposition, and optional rationale; rejected proposals remain available for analysis. |
| FR-DEC-05 | Meridian must produce draft minutes from reviewed meeting records and make them editable before finalization. | Finalization creates an immutable version and never silently sends or files the minutes externally. |
| FR-DEC-06 | A founder can search a decision timeline by topic, meeting, owner, status, and natural-language question. | Each result exposes its decision history and source citations within the caller’s permissions. |

### F. Resolution management and execution (V2)

| ID | Requirement | Acceptance condition |
|---|---|---|
| FR-EXEC-01 | A confirmed board decision can create one or more execution commitments with owner, accountable team, due date, status, and source decision. | Every commitment points back to the decision and its evidence; status changes are audited. |
| FR-EXEC-02 | The system must distinguish a draft action item from a formally approved resolution and from an external task. | The UI shows their state and authority separately; no draft becomes an external task automatically. |
| FR-EXEC-03 | Meridian can route a reviewed commitment to an approved external task/notification integration after explicit confirmation. | The external ID, delivery result, and link are stored; failed delivery does not falsely mark the action delivered. |
| FR-EXEC-04 | The system must notify owners of due, overdue, changed, and blocked commitments according to configured policy. | Recipients can see why they received the reminder and the decision that originated it. |
| FR-EXEC-05 | The next meeting’s preparation must surface unresolved, overdue, and materially changed commitments. | The agenda/pack identifies the relevant decision, owner, status, and last evidence update. |
| FR-EXEC-06 | Formal voting and e-signature must remain a policy-controlled integration. | Before release, the product documents supported jurisdictions, consent rules, audit requirements, and failure handling; until then, it is not marketed as a legally complete resolution system. |

### G. Strategic intelligence and cross-module context (V3)

| ID | Requirement | Acceptance condition |
|---|---|---|
| FR-INT-01 | Authorized users can retrieve linked board, finance, product, hiring, and operating context through one evidence-grounded interface. | Every cross-module datum states source, retrieval time, and access basis. |
| FR-INT-02 | Meridian can recommend agenda topics based on overdue commitments, decision risk, missing pre-read context, and configured operating signals. | Recommendations are ranked, explainable, editable, and never published automatically. |
| FR-INT-03 | Meridian can detect potential conflicts, stale decisions, and contradictions across source records. | It reports uncertainty and evidence rather than declaring an unsupported truth. |
| FR-INT-04 | The product can produce board-ready performance summaries from connected systems. | A human reviews the figures, scope, period, and citations before the content enters a published pack. |

## 9. AI governance and quality requirements

### Allowed AI behavior

- Extract typed candidate entities, relationships, actions, and decisions from supplied content.
- Draft agendas, summaries, minutes, reminders, board-pack sections, search plans, and contextual answers.
- Retrieve and synthesize only access-authorized, attributable sources.
- Flag uncertainty, gaps, stale material, conflicts, and missing evidence.

### Prohibited autonomous behavior

- Mutating the approved institutional-memory graph.
- Approving a decision, vote, resolution, owner, deadline, or e-signature.
- Sending an external email, calendar invitation, Slack/Teams notification, or task without human confirmation.
- Fabricating a citation, source quote, participant position, or answer beyond retrieved evidence.
- Revealing content that a caller cannot access, including through a graph quote or multi-hop relationship.

### Quality requirements

- Every substantive answer must cite the source passages used.
- Graph facts shown to users must originate from approved, provenance-backed claims.
- The extraction evaluation must report failures as well as surviving claims, segmented by model, prompt, ontology, relation, and reason.
- Retrieval evaluation must compare hybrid and vector-only retrieval with a fixed gold graph, shared plan, strata-specific results, grounding quality, and RBAC negative cases.
- Prompts and ontology are versioned. Any change that claims an improvement must include a reproducible baseline comparison.

## 10. Data model and lifecycle

### Primary objects

| Object | Required relationships / fields |
|---|---|
| Workspace | Members, policy, meetings, documents, integrations, audit scope. |
| Meeting | Agenda versions, attendees, board pack, transcript/notes, minutes versions, decisions, actions. |
| Document | Source URI, raw text, hash, version, sensitivity, pack membership, chunks, metadata. |
| Chunk | Text, offset span, embedding, sensitivity, graph bridge UUID. |
| Entity | Canonical source name, ontology type, attributes, mentions. |
| Decision | Status, topic, meeting, rationale, evidence, stakeholders, owner, effective period, supersession links. |
| Proposed change | Candidate entity/relationship, confidence, source span, provider/prompt/ontology provenance, review status. |
| Resolution | Formal decision artifact, voter/approver state, policy, attached documents, signing state. |
| Commitment | Originating decision, owner/team, deadline, status, evidence updates, external task links. |
| Audit event | Actor, action, target, previous/current state where appropriate, time, request/integration result. |

### Lifecycle rules

1. Source content is retained as the basis for derived claims.
2. Ingestion derives chunks, embeddings, mentions, candidate entities, and candidate relationships.
3. Verification either creates a pending proposal or quarantines the failed relationship; it never silently discards it.
4. Human approval commits a graph mutation idempotently and records an append-only history snapshot.
5. A decision is revised through a new decision/version and explicit relationship, especially `SUPERSEDES`; historical facts remain queryable with their period/status.
6. Published agenda, board-pack, minutes, and resolution artifacts are versioned. Editing creates a new version rather than rewriting historical records.

## 11. Non-functional requirements

| Area | Requirement |
|---|---|
| Security | Encryption in transit and at rest; least-privilege roles; pre-retrieval authorization; audit records for access, review, publication, sharing, and integration actions. |
| Privacy | Sensitive content must not be placed in prompts or logs for unauthorized callers; third-party processors must be explicit, configurable, and contractually approved. |
| Reliability | Design for 99.9% service availability after production readiness; durable source storage, backups, restore exercises, and idempotent retry for integrations. |
| Performance | Board workspace and published pack metadata should load in <=3 seconds at P95 under target load. A grounded interactive answer should return in <=10 seconds at P95, excluding a visible provider outage/degraded state. |
| Explainability | Answers, proposals, review findings, and recommendations must expose supporting evidence and status; the UI must distinguish source facts, approved graph facts, drafts, and inferences. |
| Accessibility | Web UI meets WCAG 2.2 AA for primary workflows, keyboard navigation, and readable source/citation interactions. |
| Observability | Capture request IDs, latency, provider/model, retrieval plan, denial counts, extraction failures, integration delivery result, and user-visible errors without logging unauthorized content. |
| Scalability | Design candidate retrieval for a graph larger than the demo vocabulary; do not put all entity names into a prompt at production scale. |
| Data retention | Workspace policy controls transcript, recording, and source retention. Deletion/retention legal policy must be defined before production claims; derived records follow the policy and preserve audit requirements. |

## 12. Architecture and integration boundary

### Product architecture

```text
Meridian web application / API
  ├─ Identity, workspace, board policy, meeting and pack services
  ├─ Callosum memory service
  │    ├─ Postgres + pgvector: sources, chunks, RBAC, proposals, audit, versions
  │    └─ Neo4j: approved entities, relationships, chunk bridge nodes
  ├─ Workflow service: decisions, commitments, reminders, publication
  └─ Integration adapters: calendar, email, video/transcription, e-signature, task tools, Slack/Teams, operating-data systems
```

### Build, reuse, and integrate

| Decision | Scope |
|---|---|
| Reuse | Identity, role framework, notification primitives, shared context, search/RAG platform, user profiles, and organization data where Meridian provides them. |
| Build | Board workspace, meeting lifecycle, agenda/pack workflow, review UX, decision/resolution model, provenance UI, commitment tracking, board-specific policies, and product analytics. |
| Integrate | Calendar, email, conferencing/transcription, e-signature, task systems, Slack/Teams, finance/CRM/HR data, and model inference providers. |

### Current implementation boundary

The repository currently provides a Python CLI proof-of-foundation: document ingestion, evidence verification, human proposal approval, Postgres/Neo4j bridge, permission-filtered hybrid retrieval, deterministic evaluation seeding, and tests. It does **not** yet provide a web API/UI, workspace/meeting models, agenda/pack objects, external integrations, formal resolutions, action delivery, production authentication, migrations, deployment, monitoring, or production retention policies. The roadmap must treat each missing capability as work, not as implied by the prototype or PRD.

## 13. Success measures

### Product outcomes

| Outcome | Metric | Target and measurement |
|---|---|---|
| Faster preparation | Median founder active preparation time per meeting. | <=30 minutes for a repeat meeting after the workspace has three completed meetings; measured by in-product activity plus validated research interviews. |
| Less manual work | Reported manual preparation effort versus pre-onboarding baseline. | >=80% reduction for successful pilot teams; measured after three meetings. |
| Complete record | Meetings with a published pack, reviewed minutes, decisions, and linked actions as applicable. | 100% of participating pilot meetings. |
| Fast recall | Time from question submission to an evidence-grounded decision answer. | <=10 seconds P95 for supported content and provider availability. |
| Execution continuity | Approved decisions with owner and tracked commitment when execution is required. | 100% in pilot workspaces; exclusions must be explicitly marked “no execution required.” |
| Adoption | Founder workspaces using Meridian for most board preparation. | >=40% of onboarded pilot founders by the end of their third month. |

### Trust and quality guardrails

| Guardrail | Measure | Release threshold |
|---|---|---|
| Evidence validity | Proposed relationships that fail quote verification. | Reported by relation/model/prompt; no silent loss. Threshold is used for model/prompt comparison, not hidden. |
| RBAC | Unauthorized secret exposure in vector, graph, retrieved chunks, answers, logs, or citations. | Zero tolerance; release blocker. |
| Grounding | Correct entity grounding, false-positive rate, and traversal given correct grounding. | Baseline recorded per corpus; regressions require investigation and explicit approval. |
| Human control | Consequential external actions or memory writes completed without recorded approval. | Zero tolerance; release blocker. |
| Citation coverage | Substantive answer claims linked to accessible evidence. | Measured in golden evaluation and pilot review; unsupported claims are failures. |

## 14. Analytics and experiment design

- Instrument meeting creation, agenda generation/edit/publish, pack review finding disposition, document ingestion, decision proposal/review, query/citation open, commitment status, reminder delivery, and integration failure.
- Track outcome metrics by workspace age, company stage, role, meeting type, document volume, and integration adoption without exposing sensitive content in product analytics.
- Run the retrieval evaluation by stratum: lookup, relational, multi-hop, temporal, adversarial grounding, negative grounding, and RBAC.
- Keep the gold graph distinct from model extraction so retrieval performance is not confused with extraction variance.
- Treat the corpus as an evaluation asset. Expand it intentionally with decision reversals, aliases, conflicting evidence, vague references, multiple document types, and realistic noise.

## 15. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Hallucinated or polarity-inverted decisions damage trust. | Typed schema, mandatory contiguous evidence, verifier/quarantine, human approval, live regression tests, and relationship-specific evaluation. |
| A confidential quote leaks through graph traversal. | Source-query filters, all-path edge gate, fail-closed missing provenance, RBAC negative tests, and security review before each retrieval change. |
| Founders do not adopt another tool. | Start with existing material/import paths, prove reduced preparation time, keep workflows founder-simple, and integrate rather than replace familiar tools. |
| The product overreaches into legal governance. | Clearly scope resolution/e-signature support; require policy/jurisdiction review before legal claims. |
| Integration failure creates false confidence. | Explicit user confirmation, idempotent delivery, status/error visibility, reconciliation jobs, and no automatic success assumption. |
| Entity naming/grounding breaks as the corpus grows. | Candidate retrieval, alias policy, abstention evaluation, corpus expansion, and measurable baselines before modifying the frozen core. |
| Sensitive data retention conflicts with company policy. | Configurable retention/deletion policy, processor inventory, workspace controls, and legal/security sign-off before production. |

## 16. Release acceptance criteria

### Foundation release

- All fast deterministic tests pass; live-provider tests run intentionally and their provider/model are recorded.
- A seeded evaluation reproduces the baseline and protects the confidential RBAC case.
- A normal ingestion demonstrates proposal review, a verified edge, a quarantined invalid edge, approved graph retrieval, and citation-backed answers.
- Documentation distinguishes implemented behavior from planned Meridian workflow behavior.

### V1 pilot release

- A founder can create a workspace and meeting, assemble/review/publish a board pack, run a meeting view, review decisions/minutes, and retrieve approved historical context.
- Every published artifact and approved decision has version/audit history and correct permissions.
- No external communication or consequential action occurs without confirmation.
- Accessibility, security threat model, backup/restore, observability, and pilot-support procedures are complete.
- Pilot results demonstrate the V1 product outcome measures or identify a documented reason for variance.

### V2 and V3 release gates

- V2: decisions create reviewed commitments; delivery/retry and status reconciliation are verified; the next meeting surfaces unresolved work correctly.
- V3: every recommendation is evidence-backed and reviewable; cross-module authorization is enforced; proactive intelligence is evaluated against a defined baseline and has a safe abstention/failure behavior.

## 17. Open decisions that must be resolved before the relevant checkpoint

1. Identity provider, tenancy isolation model, and production authorization service.
2. Supported jurisdictions and corporate-record policy for resolutions, voting, and e-signature.
3. Initial integration set and source-of-truth precedence for calendar, tasks, finance, CRM, HR, and conferencing data.
4. Transcript/recording consent, retention, deletion, and redaction policy.
5. Data processor/model hosting policy, customer key management requirements, and regional residency requirements.
6. Pilot cohort definition, pricing hypothesis, support model, and success baseline collection.
7. Exact API and web-application technology choices; these are implementation choices to be made only at the corresponding foundation checkpoint, not assumed by the current CLI prototype.
