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

## Frontend — ⏸️ FROZEN with P3 (maintainer)

**The whole frontend line is on `master`** (merged 2026-07-26, PRs #25 + #27 + #24). The long-lived
`feat/frontend-*` branches are history, not work in progress.

- **Design system (v2 "Calm Desk"):** light-mode only; blue `#2563EB` = action; violet `#6D28D9` reserved for Institutional Memory. Token layer, primitives, white sidebar, persistent collapsible AI rail, elevation + typography ramp, brand mark / icons / favicon. See [frontend/DESIGN.md](./frontend/DESIGN.md).
- **Routes shipped:** dashboard, calendar, meetings, documents, settings, entity-conflicts, `/memory` (knowledge graph + provenance timeline + ontology bars, closes #13), `/decisions` (#37), `/packs` (#46), `/minutes` (#48), `/resolutions` (#60), `/commitments` (CP7 contract).
- **Data honesty is the standing constraint.** Two rounds of fabricated figures were found and removed — repository metadata shown as memory coverage, an invented health %, a contradictory growth series, invented assistant citations, and unwired review-queue counts. Numbers on screen trace to a source or are labelled "not measured". Chart rules live in `frontend/DESIGN.md`.
- **Settled 2026-07-28 — the product frontend is Next.js `frontend/`.** The Vite glassmorphism prototype at `frontendglass/meridian-glass/` is a visual reference only: it does not get wired to the P3 API and no further work goes into it. It stays in the tree for now; removing it is a separate deliberate commit. See [memory.md](./memory.md).
- **Both open items from this list are closed:** `/commitments` shipped against CP7, and `decision_stance` now resolves to the board directory (the stale `board_member_id` "coming in CP5" note is gone). The responsive/mobile AI rail is **not** done — it is deferred with the rest of P3, not pending.
- **Still mock-backed:** `/entity-conflicts` reads `lib/api.ts`. It sits off the demo path and has no backend module, so it was left alone at the freeze rather than swapped.

## Product P3 — Authenticated API — ⏸️ FROZEN (feature-complete, exit gate NOT claimed)

**Frozen 2026-08-01** at `caf650d`, migration head `0017_principal_identity`. Feature work stopped here so the remaining runway to the November target goes to the writeup, diagrams, demo and deployment.

**The product track stays at 3 of 13.** P3 is frozen, *not* accepted: of its three exit criteria, workspace authorization is **met**, draft/approved/withheld is **partial** (failed and loading states are CP-F, deferred), and the keyboard/accessibility smoke checks are **not met** (CP-G, deferred). Counting it as accepted would make the roadmap say something the evidence does not support. Full scoring in the [freeze record](./docs/reviews/2026-08-01-p3-freeze.md).

- **Auth is real.** OIDC against Keycloak (compose service + realm import), an httpOnly signed-cookie session, and workspace selection re-validated against `membership` on every request. The session holds an identity and a choice — never a clearance, role or permission, so revoking a membership takes effect on the *next request* rather than at session expiry.
- **`workspace_id` and `clearance` never come from a request.** Three layers hold that: `meridian/tenancy.py` raises rather than defaulting, `deps.current_principal` is the only path to a `Principal`, and a test walks the OpenAPI schema and fails the build if any endpoint declares either (ADR-013).
- **Nine `lib/*` modules talk to the real API** through `lib/http.ts`: agenda, board members, commitments, decisions, documents, meetings, minutes, packs, resolutions. **At the freeze: 61 API operations** across 44 paths and 10 routers (the nine domain routers plus `auth`; 55 of the 61 operations are the domain routers', 6 are `auth`'s) — the surface has grown since; see the 2026-08-13 re-measurement below. Every write carries `expected_version`; every mismatch is a 409, and the client acts on it rather than reporting it.
- **Three remain local, each a recorded exception, not a pending swap:** `graph` and `assistant` are real-data snapshots deferred to P6 (#100); `insights` was audited tile by tile in CP-E — every figure is traceable to a file in this repo or is `null` with the reason recorded inline.
- **Deferred to P9 (#93):** CP-F failed/loading states, CP-G keyboard + accessibility verification, CP-H exit gate. **Accessibility is designed to WCAG 2.2 AA and never audited** — deferring CP-G defers the verification, not the standard, and any claim must carry that qualifier.
- **Verified at the freeze commit** `caf650d`, against real Postgres and Neo4j: 610 backend passed (gated) · 180 frontend · `tsc --noEmit` clean · build green, 15 routes · mechanism gate 22/22 candidate recall, 21/21 traversal (100% mean), RBAC fail-closed 1/1, `eval/mechanism.csv` **byte-identical**.
- **Re-measured on `master` `7cbfa61` (2026-08-03): 612 backend passed** (0 failed, 5 deselected) · **168 frontend passed**, 10 suites. The frontend count is **176 in 11 suites** on this branch, which adds the header/session tests.
- **The frontend count went DOWN, 180 → 168, and that is not a regression.** All −12 come from the two files rewritten in `9d11390` when the last mocks were swapped: `commitments.test.ts` 23 → 12 cases and `decisions.test.ts` 6 → 5. Mock-shape assertions were replaced by real-contract ones; the suite count is unchanged at 10 and nothing was silently dropped. Recorded because a test count that falls between two documents is exactly the kind of number a reader is right to distrust.
- The mechanism gate was **not** re-run at `7cbfa61`; the byte-identity claim above still belongs to `caf650d`.
- **Not run at the freeze:** a clean-volume migration replay (destructive to the local volume; commands are in the freeze record).

### Re-measured 2026-08-13 — a regression found, and closed the same day

Everything above describes `caf650d` and `7cbfa61` and stays as written; it is the record of
what was true then. This is the current state, measured rather than carried forward.

**The P3 acceptance decision is unchanged.** The product track stays at **3 of 13**, P3 stays
frozen and unaccepted for the reasons in the freeze record. What follows is a *current
verification* result, not a re-scoring of that checkpoint — the 26 failures below are not P3
exit criteria, and nothing here says P3 failed.

| | At the freeze (`caf650d`) | `282380c`, earlier 2026-08-13 | Master `fda0be2`, now |
|---|---|---|---|
| Gated backend | 610 passed | 608 passed, **26 FAILED** | **635 passed, 0 failed** |
| Fast backend | — | 218 passed | **219 passed**, 31 skipped, 5 deselected |
| Frontend | 180 passed | 208 passed, 14 suites | **208 passed, 14 suites** |
| API surface | 61 ops / 44 paths / 10 routers | 69 ops / 52 paths / 12 routers | **69 ops / 52 paths / 12 routers** |
| Migration head | `0017_principal_identity` | `0020_meeting_importance` | **`0021_fix_composite_fk_cascades`** (21) |
| ADRs | 15 | 15 | 15 |

**Master is green again as of `fda0be2`.** The middle column is kept rather than overwritten,
because a regression that existed for four days and was found by measurement is part of the
record, not an embarrassment to tidy away. What follows describes that column.

- **The gated suite was not clean at `282380c`:** `608 passed, 26 failed`, against a
  `phase.md` that claimed "612 backend passed (0 failed)" — a figure belonging to `7cbfa61`.
- **The 26 predated the frozen-core remediation.** They reproduced identically on master and
  on `fix/frozen-core-and-audit-integrity`; the only difference between those runs was four
  intentionally removed tests (218 → 214 fast, 608 → 604 gated).
- **Fixed in #127, merged 2026-08-13** as `0021_fix_composite_fk_cascades`. Two causes, not
  one: `0019` had dropped `ON DELETE` semantics on several composite foreign keys, **and**
  `_cleanup()` in the resolution and commitment tests never deleted `membership` rows. The
  second cause was not in the issue and would not have been found by reasoning backwards from
  the migration — it was found by reproducing first.
- **Where they fall:** `test_commitments.py` (11), `test_resolutions.py` (11), and one each in
  `test_decisions.py`, `test_principal_identity.py`, `test_meetings_api.py`,
  `test_auth_session.py`. Exceptions: 66 `ForeignKeyViolation`, 6 `AssertionError`, 3
  `NotNullViolation`, the violations occurring on `workspace` deletes.
- **The suspected cause was recorded as a hypothesis and only half of it was right.** #122
  named `0019_composite_tenant_fks` as a suspicion, not a finding: it rewrote 16 foreign keys
  as composite `(id, workspace_id)` keys, of which only 11 carried an explicit `ON DELETE`
  clause, and one of the failures was `test_cascade_delete_on_meeting_deletion`. That half held.
  The other half — the missing `membership` teardowns — was nowhere in the issue. **Recording
  the guess as a guess is what left room to find the part the guess had missed.**
- **CI could not see any of it, and now can.** `.github/workflows/ci.yml` ran
  `pytest -m "not llm" -q` with no `CALLOSUM_RUN_INTEGRATION=1`, so it exercised the fast suite
  only and reported green for four days while 26 gated tests failed (#123). #127 set
  `CALLOSUM_RUN_INTEGRATION: "1"`, and the gated tier now runs on every push. Note the `llm`
  exclusion did not disappear — it moved to `addopts` in `pyproject.toml`, so it is no longer
  visible in the workflow itself.
- **The mechanism baseline is intact.** Clean-room run at `282380c` on 2026-08-13, from empty
  volumes: migrations `0001`→`0020` applied without error (the chain has since grown to `0021`), candidate recall 22/22, gold-seeded
  traversal 21/21 (100% mean), RBAC fail-closed 1/1, and the 30 appended `eval/mechanism.csv`
  rows **byte-identical** to the previous run. This supersedes the note above that the gate had
  not been re-run since `caf650d`.
- **What byte-identical does and does not prove here.** It proves the research baseline did not
  move. It does **not** clear the frozen-core edits that shipped in #113: `acl_grant` has no
  writer anywhere in the repo, so the widened predicate was inert during the run, and
  `evaluate.py` seeds the gold graph positionally, so the changed `workspace_id` parameter fell
  through to its old behaviour. The gate was structurally unable to reach either change.

## Product P4 — Board workspace, members, and source intake — 🟩 IN PROGRESS

**Not accepted, and the 3/13 count does not move.** `rules.md` §4's 2026-08-13 amendment
makes phase order advisory — a phase may begin before the previous one's exit gate is
claimed — but it is explicit that only an exit gate advances the accepted count. P3's gate
is unclaimed and P4's has not been attempted, so the product track stays at **3 of 13**.

| P4 work item | State |
|---|---|
| Members | ✅ shipped early, as P2 CP5a / CP5b |
| Document intake / import | ✅ merged (PR #128) |
| Metadata / sensitivity | ✅ merged (#128) — clearance ladder 0–3 |
| Duplicates | ✅ merged (#128) — SHA-256, tenant-scoped by `0022_doc_content_hash_uq` |
| Processing / quarantine state | ✅ merged (#128) — `GET /api/documents/quarantine` |
| Versions | ⬜ not started |
| Workspace / meeting assignment | ⬜ not started |
| P4 exit gate | ⬜ not attempted |

**Exit criteria, and where they stand.** The phase exits when "membership is
authorized/audited; document lifecycle is visible; restricted titles, text, quotes, graph
facts, and hints cannot leak." The third is the one recent work moved most: `list_quarantine`
took no `clearance` argument at all, so a quarantine row's quote, proposed graph fact and
document id were readable at any clearance within the workspace (#128). Membership
authorisation was also not re-derived per request on the `prep` router, including its write
(#134). Neither is evidence the gate passes — they are two defects that would have failed it.

- **Source intake is deliberately text-only.** `IntakeDocumentRequest` takes `raw_text`;
  there is no multipart upload. `FEATURES.md` still lists PDF/DOCX/PPTX parsing and OCR as
  future work, so this is scope, not omission — see #140.
- **Recorded gap, no owner yet: intake has no sensitivity ceiling.** A clearance-1 principal
  may file a sensitivity-3 document. Raised during #128's review and deliberately not decided
  there; it is live behaviour now and wants a call rather than a quiet patch.
- **Chunk and document ids are derived** (`uuid5` over workspace + content hash + ordinal),
  so a crashed intake replays onto the same graph nodes rather than orphaning a second set.
  The workspace is in the key because `0022` permits two tenants to hold byte-identical
  documents, and keying on the hash alone would have made `MERGE` fuse their bridge nodes.

## Measured on `a0c1f4d` (2026-08-22)

CI run 32588329583 on `master` — a real run against Postgres and Neo4j, not a collection.

| | |
|---|---|
| Backend, gated | **700 passed**, 5 deselected |
| Backend, ungated selection | 235 |
| Frontend | **218 passed**, 15 suites |
| API | **70 operations** / 53 paths / 12 routers |
| Migration head | `0022_doc_content_hash_uq` (22) |
| Commits | 414 |

The mechanism gate is **not** part of CI and was not re-run for this figure; the byte-identity
claim recorded above still belongs to the run it names.
