# Meridian / Callosum — Phases & Status

Where the project is, at a glance. Detail lives in [ROADMAP.md](./ROADMAP.md), the release notes under `docs/releases/`, and the review records under `docs/reviews/`.

Legend: ✅ done/frozen · 🟩 in progress · ⬜ not started

## Research track — ✅ CLOSED & FROZEN

- R0–R13 accepted (14/14). Baseline frozen at tag **`eval-baseline-v3`** (code + M12–M16 corpus + gold + eval CSVs), immutable.
- Core thesis: **verified knowledge-graph construction** — no edge exists unless its verbatim evidence quote is located in the source; rejects are quarantined, not dropped.
- Deterministic metric = graph-fact recall / gold-seeded 2-hop traversal (answer text is not deterministic under hosted LLMs).

## Product P1 — Multi-tenancy — ✅ COMPLETE

- `workspace_id` across Postgres (RLS ENABLE+FORCE, non-superuser app role) and Neo4j (entity-partitioned MERGE identity + scoped reads via the query gateway).
- Hardening line shipped and re-frozen: `meridian-p1` → `p1.0.1` (conflict-scan tenant scope) → `p1.0.2` (Neo4j query gateway / defect class D-001) → `p1.0.3` (deterministic mechanism eval gate) → **`p1.0.4`** (workspace-scoped `entity_conflict` unique key). Published to origin.

## Product P2 — Durable product domain — 🟩 PHASED (backend, Devguru)

Measure-first, one aggregate root per checkpoint (own migration → domain module → tests).

| CP | Aggregate | Status |
|---|---|---|
| CP1 | `Meeting` | ✅ merged (PR #17) |
| CP2 | `AgendaItem` | ✅ merged (PR #20) |
| CP3 | `BoardPack` / minutes | ⚠️ **skipped out of order** — recorded exception, owner Devguru-codes, issue #23 |
| CP4 | `Decision` / `DecisionStance` | 🟩 in review (PR #22) |

- **CP3 skip:** CP4 took the `0009` migration slot that issue #21 had reserved for `0009_board_pack`. The chain is still linear and valid; board pack becomes `0010`. Recorded per the ROADMAP operating rule (exception needs an owner + due checkpoint).
- **CP4 open change:** `record_stance()` has no decision-status guard (votes remain mutable on an `approved`/`rejected`/`superseded` decision) and its upsert resets `created_at`, losing audit history. Review posted on PR #22.
- Deferred: retirement of the frozen-query gateway allowlist (rides the next planned retrieval change).

## Frontend — 🟩 IN PROGRESS (maintainer)

- **v1 (shipped, branch `feat/frontend-design-system` @71df854):** violet-on-zinc dual-theme "Situation Room" design system + primitives + shell + Calendar #16 + dashboard. Kept as a rollback baseline.
- **v2 (branch `feat/frontend-redesign-v2`):** rebuild the look from scratch, keep the implemented features. **Light-mode only; blue `#2563EB` = action; violet `#6D28D9` = Institutional Memory only.** Persistent collapsible AI rail. New token layer, primitives, white sidebar, dashboard (Board Readiness). See [frontend/DESIGN.md](./frontend/DESIGN.md).
  - Done: tokens, primitives, shell, AI rail, dashboard re-skin, DESIGN.md rewrite, 3-level elevation + typography hierarchy pass, brand mark / icons / favicon, design sidecar regenerated.
- **Glass Board OS (current, branch `feat/frontendglass-board-os`):** a separate Vite + React prototype at `frontendglass/meridian-glass/` exploring a glassmorphism treatment of the same Board OS surfaces.
  - The three branches are one **linear stack**, not competing alternatives: `master` → `feat/frontend-design-system` → `feat/frontend-redesign-v2` → `feat/frontendglass-board-os`.
  - **Open question:** the repo now carries two frontends — Next.js `frontend/` and Vite `frontendglass/meridian-glass/`. Whether the glass prototype replaces, feeds, or is dropped from `frontend/` is undecided and must be settled before P3 wires a real API.
- Next: land the stack on `master`; then remaining page rebuilds (Calendar, Meetings, Documents, Settings, Entity Conflicts), responsive/mobile AI rail, Graph Viewer (#13).

## Product P3 — Web API layer — ⬜ NOT STARTED

- The frozen core is CLI/Python; the frontend runs entirely on mocks. A real API (FastAPI, stack already installed) is the P3 gate that replaces the mock `lib/*` layer.
