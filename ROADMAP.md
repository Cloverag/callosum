# Callosum — Roadmap & Checkpoints

Where the project is, what is done, and what comes next. Legend:
**✅ done · 🔄 in progress / next · ⬜ planned · 🔒 deliberately out of scope (for the thesis)**

> ## 📍 You are here: **Checkpoint 7 — Temporal reasoning + ontology v2**
> Tagged `eval-baseline-v2` (`master`). Two documents in the corpus (polarity + temporal),
> reproducible stratified evaluation, canonical entity grounding. Next up: **Checkpoint 8 —
> entity aliases (Board Meeting 14).**

---

## Phase A — Research prototype (the thesis)

This is the current focus. Each checkpoint is a demonstrable capability backed by the
evaluation, not a feature guess.

| # | Checkpoint | State | Evidence |
|---|---|---|---|
| CP0 | Architecture decided (hybrid graph+vector, the shared-chunk bridge) | ✅ | `docs/architecture.md` |
| CP1 | Ingestion — load, hash-dedupe, chunk with char offsets, embed | ✅ | `src/callosum/ingest.py` |
| CP2 | **Verified extraction** — no edge without a located verbatim quote; quarantine | ✅ | `extract.py`, findings run 1–4 |
| CP3 | Hybrid storage — Postgres+pgvector + Neo4j joined on a shared chunk UUID | ✅ | `store.py` |
| CP4 | Retrieval + **RBAC** — planner → graph‖vector → fail-closed permission gate | ✅ | `retrieve.py`, findings run 3 (leak found+fixed) |
| CP5 | **Multi-hop traversal + canonical entity grounding** (NEL) | ✅ | findings run 5, 9 |
| CP6 | **Reproducible stratified evaluation** — gold graph, ablation, GER, CSV log | ✅ | `evaluate.py`, tag `eval-baseline-v1` |
| CP7 | **Temporal reasoning + ontology v2** (SUPERSEDES across documents, REQUESTED) | ✅ **← now** | tag `eval-baseline-v2`, findings run 12 |
| CP8 | **Entity aliases** (Board Meeting 14) — "Raj" / "Rajesh" / "R. Malhotra" = one node | 🔄 next | stresses grounding recall + precision |
| CP9 | Conflicting evidence & provenance (Board Meeting 15) — Finance 12M vs Sales 11.6M | ⬜ | |
| CP10 | Context-dependent references (Board Meeting 16) — "that proposal", "the motion" | ⬜ | |
| CP11 | Messy real-world documents — typos, interrupted dialogue, inconsistent names | ⬜ | the real test; after synthetic matrix is complete |
| CP12 | Grounding abstention / candidate retrieval — fix precision, scale the vocabulary | ⬜ | triggered by measured GER/precision gaps |
| CP13 | Thesis writeup — the V1→V2→V3 narrative + the evaluation chapter | ⬜ | `docs/findings.md` is the raw material |

**The capability matrix** (why each document exists — one capability per document):

| Doc | Capability under test |
|---|---|
| Meeting 12 | Polarity (SUPPORTED / OPPOSED / APPROVED) |
| Meeting 13 | Temporal reasoning & decision evolution (SUPERSEDES) |
| Meeting 14 | Entity grounding under aliases |
| Meeting 15 | Conflicting evidence & provenance |
| Meeting 16 | Context-dependent references |

---

## Phase B — Product prototype (frontend + real usage)

Turns the engine into something a founder actually touches. Best fit for a product/PM
collaborator — see `CONTRIBUTING.md`.

| # | Milestone | State |
|---|---|---|
| CP14 | Founder **chat UI** — question → grounded answer + citations + "withheld" notice | ⬜ |
| CP15 | **Approval-queue UI** — the human-in-the-loop review screen | ⬜ |
| CP16 | **Graph explorer** — navigate the knowledge graph visually | ⬜ |
| CP17 | Thin **API layer** (FastAPI) over the retrieval + approval functions | ⬜ |

---

## Phase C — Fully-fledged application

The long horizon: from a research prototype to a deployable product. The concrete feature
list lives in **[FEATURES.md](FEATURES.md)**. Headline pillars:

- **Connectors** — ingest from Slack, Gmail, Zoom/Meet, Drive, Notion, Confluence
- **Real-time ingestion** — new documents flow in continuously, not batch
- **Entity resolution & temporal validity** — aliases, coreference, valid-from/valid-to
- **Multi-tenancy, SSO, compliance** — teams, roles, audit, encryption, GDPR
- **Cloud deployment & scale** — managed stores, horizontal scaling, observability

---

## How to read progress

- The **evaluation is the source of truth.** A checkpoint is "done" when the eval
  demonstrates it, not when the code merges. See `docs/findings.md` and the git tags.
- **Frozen vs open** boundary lives in `CONTRIBUTING.md`. The core pipeline is frozen;
  data, questions, frontend, and analyses keep growing.
- Every ontology change is versioned and logged in `docs/ontology-changelog.md`.
