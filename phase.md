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

## Product P2 — Durable product domain — ✅ ACCEPTED (2026-07-29)

Measure-first, one aggregate root per checkpoint (own migration → domain module → tests).

| CP | Aggregate | Migration | Status |
|---|---|---|---|
| CP1 | `Meeting` | `0007_meeting` | ✅ merged (PR #17) |
| CP2 | `AgendaItem` | `0008_agenda_item` | ✅ merged (PR #20) |
| CP3 | `BoardPack` / minutes | `0010_board_pack` | ✅ merged (PR #33) |
| CP4 | `Decision` / `DecisionStance` | `0009_decision` | ✅ merged (PR #22) |
| CP5a | `BoardMember` directory | `0012_board_member` | ✅ merged (PR #42) |
| CP5b | membership wiring + `principal` scoping | `0013_principal_rls` | ✅ merged (PR #43) |
| CP6 | `Resolution` / `ResolutionVote` | `0014_resolution` | ✅ merged (PR #54) |
| CP7 | `Commitment` / `CommitmentUpdate` | `0015_commitment` | ✅ merged (PR #57) |
| CP8 | `AuditEvent` | `0016_audit_event` | ✅ merged (PR #61) |
| CP9 | notification | — | ⏸️ **deferred to P8** — recorded exception, issue #62 |
| CP10 | P2 exit gate (no migration) | — | ✅ **PASSED 2026-07-29** — [acceptance record](./docs/reviews/2026-07-29-p2-acceptance.md) |

- **Nine aggregate roots merged.** Sixteen migrations apply cleanly from an empty volume; the chain is linear.
- **P2 is ACCEPTED.** CP10 passed on 2026-07-29: full-chain downgrade and return, a round trip proved lossless against a fresh build (628 schema facts, identical), and a restore from an empty volume. See the [acceptance record](./docs/reviews/2026-07-29-p2-acceptance.md).
- **CP3 exception — closed.** CP4 took the `0009` slot CP3 had reserved, so CP3 shipped later as `0010`. Both are merged and issue #23 is closed.
- **CP5 was split** into CP5a (directory) and CP5b (membership wiring) when CP5a's review found clearance still being read from the legacy `principal.clearance` column.
- **Released:** `0011`–`0013` are frozen in tag **`meridian-p1.0.5`** (2026-07-28) — 176 passed, mechanism gate byte-identical. Three limitations carried forward; see the [freeze note](./docs/reviews/2026-07-28-meridian-p1.0.5-freeze.md).
- **CP9 deferred to P8** (owner Devguru-codes, issue #62). Nothing in P2 produces a notification — no dispatcher, adapter, scheduler or trigger — so the table would enter the frozen chain designed against zero call sites. P8 owns notification delivery, alongside the retry state CP7 already models on `commitment`. CP10 depends on CP8, not CP9. **Do not close CP9 by adding an empty table.**
- **Test count:** 263 backend (gated, real Postgres) and 121 frontend.
- Deferred: retirement of the frozen-query gateway allowlist (rides the next planned retrieval change).

## Frontend — 🟩 IN PROGRESS (maintainer)

**The whole frontend line is on `master`** (merged 2026-07-26, PRs #25 + #27 + #24). The long-lived
`feat/frontend-*` branches are history, not work in progress.

- **Design system (v2 "Calm Desk"):** light-mode only; blue `#2563EB` = action; violet `#6D28D9` reserved for Institutional Memory. Token layer, primitives, white sidebar, persistent collapsible AI rail, elevation + typography ramp, brand mark / icons / favicon. See [frontend/DESIGN.md](./frontend/DESIGN.md).
- **Routes shipped:** dashboard, calendar, meetings, documents, settings, entity-conflicts, `/memory` (knowledge graph + provenance timeline + ontology bars, closes #13), `/decisions` (#37), `/packs` (#46), `/minutes` (#48), `/resolutions` (#60).
- **Data honesty is the standing constraint.** Two rounds of fabricated figures were found and removed — repository metadata shown as memory coverage, an invented health %, a contradictory growth series, invented assistant citations, and unwired review-queue counts. Numbers on screen trace to a source or are labelled "not measured". Chart rules live in `frontend/DESIGN.md`.
- **Settled 2026-07-28 — the product frontend is Next.js `frontend/`.** The Vite glassmorphism prototype at `frontendglass/meridian-glass/` is a visual reference only: it does not get wired to the P3 API and no further work goes into it. It stays in the tree for now; removing it is a separate deliberate commit. See [memory.md](./memory.md).
- **Next:** `/commitments` against the merged CP7 contract; then resolving `decision_stance` to the board directory (`decisions.ts` still says `board_member_id` is "coming in CP5" — CP5a shipped it), and the responsive/mobile AI rail.

## Product P3 — Authenticated API — 🟩 IN PROGRESS

- **Auth is real.** OIDC against Keycloak (compose service + realm import), an httpOnly signed-cookie session, and workspace selection re-validated against `membership` on every request. The session holds an identity and a choice — never a clearance, role or permission, so revoking a membership takes effect on the *next request* rather than at session expiry.
- **`workspace_id` and `clearance` never come from a request.** Three layers hold that: `meridian/tenancy.py` raises rather than defaulting, `deps.current_principal` is the only path to a `Principal`, and a test walks the OpenAPI schema and fails the build if any endpoint declares either (ADR-013).
- **Six of seven mock modules now talk to the real API**: resolutions, board members, agenda, meetings, packs, minutes. `decisions` remains.
- **Four mocks have no backend and are untouched** (CP-E): `documents`, `insights`, `graph`, `assistant`.
- **Test counts:** 460 backend (gated, real Postgres) · 159 frontend.
