# Callosum — Feature Vision (toward a fully-fledged application)

What Callosum is today (a research prototype with a verified-extraction engine and a
reproducible evaluation) versus what it would take to become a product a company runs.
This is a **direction document**, not a commitment — it exists so the scope is legible and
so every future feature can be justified against the evaluation baseline rather than added
on intuition.

Legend: **✅ built · 🔄 in progress · ⬜ future · 🔒 explicitly out of scope for the thesis**

---

## 1. Ingestion & Connectors

Today the system ingests local files by hand. A real institutional-memory product listens
to where knowledge actually happens.

| Feature | State |
|---|---|
| Manual file ingest (txt / transcript), hash-dedupe, chunking with offsets | ✅ |
| PDF / DOCX / PPTX parsing | ⬜ |
| **Slack** connector (channels, threads) | ⬜ |
| **Gmail / Outlook** connector (decisions live in email) | ⬜ |
| **Zoom / Google Meet / Teams** transcript ingestion | ⬜ |
| **Google Drive / Notion / Confluence / Jira** sync | ⬜ |
| Audio / video → transcription (Whisper) then ingest | ⬜ |
| OCR for scanned documents and images | ⬜ |
| **Real-time / streaming ingestion** (new content flows in continuously) | ⬜ |
| Incremental re-ingestion on document change | ⬜ |

## 2. Knowledge & Intelligence

The core engine. This is where the thesis contribution lives; the future items extend it.

| Feature | State |
|---|---|
| **Verified extraction** — no edge without a located verbatim quote | ✅ |
| Quarantine of rejected edges (the extraction process is the dataset) | ✅ |
| Provenance stamping (provider / model / prompt / ontology version) | ✅ |
| Immutable version history (append-only node versions) | ✅ |
| **2-hop graph traversal** + **canonical entity grounding** (NEL) | ✅ |
| **Temporal reasoning** — SUPERSEDES across documents | ✅ |
| **Entity resolution** — aliases, coreference ("Raj" = "Rajesh Kumar") | 🔄 CP8 |
| **Grounding abstention** — know when NOT to link (precision) | ⬜ |
| **Candidate retrieval** for grounding at scale (don't dump 50k names in a prompt) | ⬜ |
| Temporal validity edges — `valid_from` / `valid_to`, "what was true in Q2?" | ⬜ |
| **Contradiction detection** — Finance says 12M, Sales says 11.6M | ⬜ |
| Confidence calibration / uncertainty surfacing | ⬜ |
| Automatic ontology suggestions (propose new relation types from data) | ⬜ |
| Multi-lingual extraction and retrieval | ⬜ |
| Proactive insights & alerts ("this decision contradicts last quarter's") | ⬜ |

## 3. Retrieval & Question Answering

| Feature | State |
|---|---|
| Planner → hybrid graph+vector → permission filter → grounded answer + citations | ✅ |
| Ablation / measurement of graph vs vector contribution | ✅ |
| Conversational memory — multi-turn follow-ups ("who else?") | ⬜ |
| Agentic multi-step reasoning over the graph | ⬜ |
| Saved / scheduled questions and digests | ⬜ |
| Answer export (PDF / share link) | ⬜ |

## 4. Human-in-the-loop & Governance

| Feature | State |
|---|---|
| Approval queue — LLM proposes, human approves; only then the graph mutates | ✅ (backend) |
| **Approval UI** — review, approve, reject, edit proposed edges | ⬜ CP15 |
| Bulk review, confidence-sorted queues | ⬜ |
| Edit / merge suggestions (entity resolution review) | ⬜ |
| Audit-trail UI — who approved what, when, from which evidence | ⬜ |
| Version-history diff view | ⬜ |

## 5. Security & Compliance

| Feature | State |
|---|---|
| RBAC clearance ladder (0 public → 4 restricted), **fail-closed** permission gate | ✅ |
| Per-object ACL grants (escape hatch) | ✅ (schema) |
| Full RBAC role hierarchy + inheritance | ⬜ |
| SSO / SAML / OAuth login | ⬜ |
| Encryption at rest & in transit | ⬜ |
| PII detection & redaction | ⬜ |
| GDPR / "right to be forgotten" deletion across both stores | ⬜ |
| Comprehensive audit logging | ⬜ |
| SOC 2 / compliance posture | 🔒 (product concern, not thesis) |

## 6. Frontend / UX

| Feature | State |
|---|---|
| Founder **chat interface** | ⬜ CP14 |
| **Approval-queue** screen | ⬜ CP15 |
| **Graph explorer** (visual navigation) | ⬜ CP16 |
| Dashboards (decisions over time, open action items, ownership) | ⬜ |
| Notifications (email / Slack / push) | ⬜ |
| Mobile / responsive | ⬜ |

## 7. Platform & Operations

| Feature | State |
|---|---|
| Local `docker compose` (Postgres+pgvector, Neo4j) | ✅ |
| Pluggable model provider (Ollama ↔ Anthropic) | ✅ |
| **Multi-tenancy** (isolated orgs / workspaces) | ⬜ |
| Cloud deployment (Kubernetes / managed services) | ⬜ |
| Managed Postgres + Neo4j, backups, disaster recovery | ⬜ |
| Horizontal scaling, background job queue for ingestion/extraction | ⬜ |
| Observability — logging, metrics, tracing, cost monitoring | ⬜ |
| Model routing & response caching (cost control) | ⬜ |

## 8. Evaluation & Quality (thesis strength — keep growing)

| Feature | State |
|---|---|
| Stratified eval (lookup/relational/multi_hop/temporal/grounding/rbac) | ✅ |
| Fixed gold graph + document-aware seeding | ✅ |
| Two-stage grounding vs traversal metrics, GER, precision, ablation | ✅ |
| CSV experiment log (diffable across runs), versioned baselines (git tags) | ✅ |
| Continuous evaluation in CI, regression gates | ⬜ |
| Larger hand-annotated benchmark (30–50+ questions, multiple documents) | 🔄 |
| Human evaluation of answer quality | ⬜ |
| Open-weight vs frontier model comparison on the same corpus | ⬜ (provider abstraction ready) |

## 9. Integrations & API

| Feature | State |
|---|---|
| CLI (`callosum …`) | ✅ |
| REST / GraphQL API | ⬜ CP17 |
| Webhooks & event stream | ⬜ |
| Slack bot ("ask Callosum") | ⬜ |
| Client SDK | ⬜ |
| MCP server (agent access to the graph) | ⬜ |

---

## Guiding principle

Callosum is not trying to be a chatbot with a database. The thesis is that a **verified,
auditable knowledge graph joined to a vector store, gated by permissions and curated by
humans**, answers organizational questions that neither store answers alone. Every feature
above is judged by whether it serves that thesis — and, in the product horizon, whether it
survives contact with messy real-world documents. Features get built when a measured gap
justifies them, not before.
