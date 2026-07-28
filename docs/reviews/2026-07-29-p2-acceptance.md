# P2 acceptance record — durable product domain and migrations

**Date:** 2026-07-29 · **Checkpoint:** CP10, the P2 exit gate (no migration)
**Master at acceptance:** `ea91a45` · **Migration head:** `0016_audit_event`
**Research baseline:** `eval-baseline-v3` — unchanged and unaffected

CP10 is a verification checkpoint. It ships no schema and no domain code; its
deliverable is evidence that P2's exit criteria hold.

## The exit criteria, and what proves each

ROADMAP P2 states three:

> migration/recovery plan is tested; invalid transitions and cross-workspace access
> are rejected; superseded/published records preserve immutable history.

| Criterion | Evidence | Result |
|---|---|---|
| Migration/recovery plan tested | Drills 1–3 below | **PASS** |
| Invalid transitions rejected | 21 tests | **21 passed** |
| Cross-workspace access rejected | 26 tests, all 9 aggregates | **26 passed** |
| Immutable history preserved | 14 tests | **14 passed** |

Full gated suite: **263 passed**, 0 failed, 5 deselected, on a clean volume with
`CALLOSUM_RUN_INTEGRATION=1` against real Postgres and Neo4j.

## Drill 1 — full-chain downgrade and return

The criterion no aggregate covered. CP1–CP8 each verified their own migration in
isolation; **nobody had reversed the whole chain.**

```
alembic downgrade base   → 16 downgrades, 0001 ← 0016, exit 0
alembic upgrade head     → 16 upgrades,   0001 → 0016, exit 0
```

Both directions clean. Every `downgrade()` in the chain is now known to execute in
sequence, not merely to exist.

## Drill 2 — a round trip must be *lossless*, not merely successful

A downgrade/upgrade cycle can succeed and still leave drift: an index not recreated, a
constraint quietly dropped, a grant lost. "It ran" is not the bar.

The schema was fingerprinted from the Postgres catalogue — columns with types,
nullability and defaults; every constraint definition; every index definition; RLS
enabled/forced flags; every policy's `USING` and `WITH CHECK`; and every
`callosum_app` grant — then compared against a **fresh build from an empty volume**.

```
round trip (downgrade base → upgrade head):  628 schema facts
fresh volume (0001 → 0016 from empty):       628 schema facts
diff:                                        IDENTICAL
```

The recovery path reproduces the schema exactly. That is what makes it a recovery
plan rather than a hope.

## Drill 3 — restore from empty

```
docker compose down -v
docker compose up -d
alembic upgrade head        → 16 migrations from empty
callosum init               → 3 principals, memberships granted
ingest + seed-eval          → gold graph seeded, 40 board edges + 1 confidential
```

Final state: 26 tables, **24 with row-level security**. The two without are
`alembic_version` (Alembic's own bookkeeping) and `sensitivity` (a global lookup of
clearance levels 0–4, identical for every tenant — `0011_control_plane_rls` revokes
runtime writes to it rather than partitioning it, which is correct for a shared
lookup).

## Mechanism gate

Run after the restore, against the reseeded gold graph:

| Check | Result | Required |
|---|---|---|
| Candidate recall | 22/22 | = total |
| Traversal recall (gold seeds) | 21/21 full, 100% mean | = 100% |
| RBAC fail-closed | 1/1 | = total |

**`eval/mechanism.csv`: 30 appended rows byte-identical to the previous run.** Across
CP6, CP7, CP8 and this gate, every run has been byte-identical — the evidence that
nine new aggregate roots and six migrations changed no retrieval or RBAC behaviour.

**Frozen core untouched.** Checked file by file against the CONTRIBUTING.md list across
the whole P2 line (`c769278` → `ea91a45`), not by eyeballing a directory diff:

| Frozen file | Across P2 |
|---|---|
| `src/callosum/ingest.py` | untouched |
| `src/callosum/extract.py` | untouched |
| `src/callosum/retrieve.py` | untouched |
| `src/callosum/store.py` | untouched |
| `schema/postgres.sql` | untouched |

Three files under `src/callosum/` *did* change and none is frozen: `identity.py` (new,
added under the CP5b tenancy exception), `cli.py` (new commands), and `__init__.py`.
Worth stating precisely, because "the frozen core is untouched" and "nothing under
`src/callosum/` changed" are different claims and only the first is true.

## What P2 delivered

Nine aggregate roots, ten migrations (`0007`–`0016`):

| CP | Aggregate | Migration |
|---|---|---|
| CP1 | `Meeting` | `0007_meeting` |
| CP2 | `AgendaItem` | `0008_agenda_item` |
| CP3 | `BoardPack` / `Minutes` | `0010_board_pack` |
| CP4 | `Decision` / `DecisionStance` | `0009_decision` |
| CP5a | `BoardMember` | `0012_board_member` |
| CP5b | membership wiring, `principal` scoping | `0013_principal_rls` |
| CP6 | `Resolution` / `ResolutionVote` | `0014_resolution` |
| CP7 | `Commitment` / `CommitmentUpdate` | `0015_commitment` |
| CP8 | `AuditEvent` | `0016_audit_event` |

Plus `0011_control_plane_rls`, a P1 patch that landed inside the P2 window.

## Recorded exceptions

Both remain recorded rather than silently closed, per the operating rule.

- **CP3 delivered out of order** (issue #23, closed). CP4 took the `0009` slot CP3 had
  reserved; CP3 shipped as `0010`. Chain stayed linear throughout.
- **CP9 (notification) deferred to P8** (issue #62, open). Owner: Devguru-codes.
  Nothing in P2 produces a notification — no dispatcher, adapter, scheduler or
  trigger — so the table would enter the frozen chain designed against zero call
  sites. CP10 depends on CP8, not CP9. **CP9 must not be closed by adding an empty
  table.**

## Limitations carried into P3

Stated so they are not rediscovered as surprises.

1. **`app.workspace_id` is an ordinary GUC.** `callosum_app` can set it to any value,
   so RLS guards application bugs, not a compromised runtime role. Unchanged since
   `p1.0.5`.
2. **Composite-FK coverage is partial.** New tenant-scoped relationships in CP5a, CP6
   and CP7 use `(id, workspace_id)`; older ones rely on an RLS-scoped existence check
   in the domain module — a real defence, but by convention. Tracked in **#41**.
3. **`audit_event.actor_principal_id` cannot use a composite FK at all**, because
   `principal` has no `workspace_id` column. The workspace half is enforced by a
   membership check in `record_audit_event()`. This is the concrete case showing the
   composite-FK rule cannot be applied mechanically — see #41.
4. **Delivery columns on `commitment` are inert.** `external_system`,
   `external_task_id`, `delivery_status` and `delivery_attempts` model retry *state*;
   nothing dispatches. P8 owns execution. FR-EXEC-03 is enforced as a CHECK constraint
   so no adapter can claim a delivery it cannot reconcile.
5. **`principal.clearance` is retained** as a deprecated bootstrap seed because it is
   declared in the frozen `schema/postgres.sql`. Demoted with `COMMENT ON COLUMN`; not
   read for any access decision.

## Verdict

**P2 is ACCEPTED.** Product track moves to **3 / 13** (`P0`, `P1`, `P2`).

The next checkpoint is **P3 — authenticated API and accessible application shell**,
which is the gate that replaces the frontend's mock `lib/*` layer with real data. The
two-frontends question was settled on 2026-07-28: the product frontend is the Next.js
app, and the Vite glass prototype is reference only.
