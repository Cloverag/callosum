# Meridian / Callosum — Phases & Status

Where the project is, at a glance. Detail lives in [ROADMAP.md](./ROADMAP.md), the release notes under `docs/releases/`, and the review records under `docs/reviews/`.

Legend: ✅ done/frozen · 🟩 in progress · ⬜ not started

## Research track — ✅ CLOSED & FROZEN

- R0–R13 accepted (14/14). Baseline frozen at tag **`eval-baseline-v3`** (code + M12–M16 corpus + gold + eval CSVs), immutable.
- Core thesis: **verified knowledge-graph construction** — no edge exists unless its verbatim evidence quote is located in the source; rejects are quarantined, not dropped.
- Deterministic metric = graph-fact recall / gold-seeded 2-hop traversal (answer text is not deterministic under hosted LLMs).

## Product P1 — Multi-tenancy — ✅ COMPLETE

- `workspace_id` across Postgres (RLS ENABLE+FORCE, non-superuser app role) and Neo4j (entity-partitioned MERGE identity + scoped reads via the query gateway).
- Hardening line shipped and re-frozen: `meridian-p1` → `p1.0.1` (conflict-scan tenant scope) → `p1.0.2` (Neo4j query gateway / defect class D-001) → `p1.0.3` (deterministic mechanism eval gate) → `p1.0.4` (workspace-scoped `entity_conflict` unique key) → **`p1.0.5`** (control-plane RLS, composite foreign keys, clearance resolved through `membership`). Published to origin.
- `p1.0.5` also carries the CP5a/CP5b P2 checkpoints: the three migrations only make sense together, so the patch-line name now spans some P2 work.

## Product P2 — Durable product domain — 🟩 PHASED (backend, Devguru)

Measure-first, one aggregate root per checkpoint (own migration → domain module → tests).

| CP | Aggregate | Migration | Status |
|---|---|---|---|
| CP1 | `Meeting` | `0007_meeting` | ✅ merged (PR #17) |
| CP2 | `AgendaItem` | `0008_agenda_item` | ✅ merged (PR #20) |
| CP3 | `BoardPack` / minutes | `0010_board_pack` | ✅ merged (PR #33) |
| CP4 | `Decision` / `DecisionStance` | `0009_decision` | ✅ merged (PR #22) |
| CP5a | `BoardMember` directory | `0012_board_member` | ✅ merged (PR #42) |
| CP5b | membership wiring + `principal` scoping | `0013_principal_rls` | ✅ merged (PR #43) |
| CP6 | `Resolution` | next free slot | ⬜ not filed — to be scoped with the backend owner |
| CP7–CP10 | commitment, audit, notification, exit gate | — | ⬜ planned |

- **Six aggregate roots merged.** Thirteen migrations apply cleanly from an empty volume; the chain is linear.
- **CP3 exception — closed.** CP4 took the `0009` slot CP3 had reserved, so CP3 shipped later as `0010`. Both are merged and issue #23 is closed.
- **CP5 was split** into CP5a (directory) and CP5b (membership wiring) when CP5a's review found clearance still being read from the legacy `principal.clearance` column.
- **Released:** `0011`–`0013` are frozen in tag **`meridian-p1.0.5`** (2026-07-28) — 176 passed, mechanism gate byte-identical. Three limitations carried forward; see the [freeze note](./docs/reviews/2026-07-28-meridian-p1.0.5-freeze.md).
- **CP6 is deliberately unfiled** — to be scoped with the backend owner rather than handed over as a spec written without him.
- Deferred: retirement of the frozen-query gateway allowlist (rides the next planned retrieval change).

## Frontend — 🟩 IN PROGRESS (maintainer)

**The whole frontend line is on `master`** (merged 2026-07-26, PRs #25 + #27 + #24). The long-lived
`feat/frontend-*` branches are history, not work in progress.

- **Design system (v2 "Calm Desk"):** light-mode only; blue `#2563EB` = action; violet `#6D28D9` reserved for Institutional Memory. Token layer, primitives, white sidebar, persistent collapsible AI rail, elevation + typography ramp, brand mark / icons / favicon. See [frontend/DESIGN.md](./frontend/DESIGN.md).
- **Routes shipped:** dashboard, calendar, meetings, documents, settings, entity-conflicts, `/memory` (knowledge graph + provenance timeline + ontology bars, closes #13), `/decisions` (PR #37).
- **Data honesty is the standing constraint.** Two rounds of fabricated figures were found and removed — repository metadata shown as memory coverage, an invented health %, a contradictory growth series, invented assistant citations, and unwired review-queue counts. Numbers on screen trace to a source or are labelled "not measured". Chart rules live in `frontend/DESIGN.md`.
- **Open question:** the repo carries two frontends — Next.js `frontend/` and Vite `frontendglass/meridian-glass/` (a glassmorphism prototype of the same surfaces, tracked on `master`). Whether it replaces, feeds, or is dropped from `frontend/` is undecided and must be settled before P3 wires a real API.
- **Next:** BoardPack + Minutes surfaces against the merged CP3 contract (`meridian/packs.py`, `meridian/minutes.py`); then calendar unit tests (#28, blocked behind #15), responsive/mobile AI rail.

## Product P3 — Web API layer — ⬜ NOT STARTED

- The frozen core is CLI/Python; the frontend runs entirely on mocks. A real API (FastAPI, stack already installed) is the P3 gate that replaces the mock `lib/*` layer.
