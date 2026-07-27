# P2 — plan for the remaining checkpoints (CP5–CP9 + exit gate)

**Status:** proposal, design-only. Nothing here authorises code.
**Author:** maintainer · **Date:** 2026-07-27 · **Master at time of writing:** `c158086`

---

## 1. Where P2 actually is

ROADMAP P2's goal names eleven object families. Six are done or in review:

| Object | State | Where |
|---|---|---|
| workspace | ✅ | P1, migration `0001` |
| member | ✅ | P1, `membership` (`0001`) |
| meeting | ✅ CP1 | `0007`, PR #17 |
| agenda | ✅ CP2 | `0008`, PR #20 |
| decision | ✅ CP4 | `0009`, PR #22 |
| pack / minutes versions | 🟡 CP3 in review | `0010`, PR #33 |
| **board** | ❌ | — |
| **resolution** | ❌ | — |
| **commitment** | ❌ | — |
| **notification** | ❌ | — |
| **audit** | ❌ | — |

P2 does not end when CP3 merges. Five object families remain, plus an exit criterion no aggregate checkpoint covers: *"migration/recovery plan is tested."*

## 2. The P2 / P8 boundary — read this before scoping anything

Resolution, commitment and notification appear in **both** P2 and P8, and conflating them is the main way this phase could balloon.

- **P2 owns the record.** Tables, lifecycle states, transition rules, version/publication semantics, ownership columns, and the *fields* that delivery will later populate.
- **P8 owns the behaviour.** Voting and e-signature policy, external task/notification adapters, retry execution, reconciliation, and progress reporting.

Concretely: P2 gives `commitment` an `external_task_id` and a `delivery_status` column and tests that they can only move through legal states. P2 does **not** call Jira. FR-EXEC-06 is explicit that voting and e-signature stay policy-controlled and unreleased, so CP6 must not imply legal validity.

## 3. Proposed checkpoints

Same discipline as CP1–CP4: one aggregate root per checkpoint, strictly sequential, migration → domain module → tests as separate commits, decision record, negative security tests, reviewed diff.

### CP5 — BoardMember directory (`0011_board_member`)

**Why first:** every remaining object references a person. `decision_stance.person_name` is currently **free text** — stances are not linked to anybody, so "show me everything Marcus opposed" cannot be answered reliably today. Resolution needs voter state and Commitment needs an owner; both would repeat that mistake if built first.

`board_member` is **not** `membership`. `membership` is the auth fact (principal × workspace → role, clearance). `board_member` is the governance directory from FR-WS-03: name, organization, role (director / observer / executive / administrator / adviser), contact method, **voting status**, active/inactive. A board member may have no login at all, so the link to `principal` is nullable.

Scope: table + RLS + lifecycle (active/inactive, never hard-deleted — historical stances must stay attributable) + a nullable `board_member_id` on `decision_stance` with a backfill path. Do **not** make it required in this checkpoint; that is a separate migration once the directory is populated.

### CP6 — Resolution (`0012_resolution`)

The formal instrument, distinct from the Decision that produced it. FR-EXEC-02 requires three things be separable: a draft action item, a formally approved resolution, and an external task. CP6 delivers the middle one.

Scope: `resolution` (source `decision_id`, text, status, `version_no` + `superseded_by_id` per the versioning rule in PRD §260) and `resolution_vote` (board member, vote, recorded_at). Published resolutions are frozen; amendment creates a new version, exactly as packs and minutes now do.

**Explicitly out:** e-signature, legal validity, jurisdiction handling. A `signing_state` column may exist as an enum with a single `not_applicable` value so P8 has somewhere to land, but nothing may claim a resolution is legally executed.

### CP7 — Commitment (`0013_commitment`)

FR-EXEC-01: owner, accountable team, due date, status, source decision, and a pointer back to the decision's evidence.

Scope: `commitment` table, lifecycle (`open → in_progress → {completed, blocked, cancelled}`), `commitment_update` for the evidence-update trail, and inert columns for external linkage (`external_system`, `external_task_id`, `delivery_status`, `delivery_attempts`). The P2 goal statement names "retries" — that means retry *state* is modelled here; retry *execution* is P8.

**The invariant to test hardest:** a commitment cannot exist without a source decision, and FR-EXEC-03's rule that failed delivery must never falsely mark an action delivered has to be structurally impossible — `delivery_status` cannot reach `delivered` without an `external_task_id`.

### CP8 — Notification (`0014_notification`)

FR-EXEC-04: owners are notified of due, overdue, changed and blocked commitments, and recipients can see *why* they received it and which decision originated it.

Scope: `notification` (recipient, kind, subject reference, reason, originating decision, state, attempts, last_error). Channels, templates and sending are P8.

This is the checkpoint most at risk of being over-built. If the answer to "what actually creates a notification in V1?" is "nothing yet, P8 does", then the honest V1 shape is a small table with a clean state machine and no producer — and that should be stated in the decision record rather than padded out.

### CP9 — Audit event (`0015_audit_event`)

PRD §251: actor, action, target, previous/current state where appropriate, time, request/integration result. Last, because it must cover every aggregate built before it.

**Must reconcile with what exists rather than duplicate it.** `query_log` already satisfies FR-MEM-09 (principal, plan, hits, denied count, answer, latency) and is the *retrieval* audit. `audit_event` is the *domain* audit — membership changes, publication, supersession, delivery confirmation. Two tables with clear, documented remits is the right answer; one table trying to be both is not.

Scope: table + RLS + a write path used by the existing aggregates for their state transitions. Retrofitting the CP1–CP8 modules to emit events is the bulk of the work and belongs here, not scattered backwards.

### CP10 — P2 exit gate (no migration)

The exit criterion no aggregate covers: *"migration/recovery plan is tested."*

Scope: a documented and **executed** restore drill — fresh volume, `0001` → head, seed, verify; a full downgrade/upgrade cycle across the whole chain, not just the newest link; the P2 acceptance record; and a ROADMAP progress update. CP1–CP4 each verified their own migration in isolation; nobody has yet proven the chain restores end to end.

## 4. Sequence and dependencies

```
CP3 (in review) ──> CP5 board_member ──┬──> CP6 resolution ──┐
                                       └──> CP7 commitment ──┴──> CP8 notification ──> CP9 audit ──> CP10 exit gate
```

CP6 and CP7 both depend only on CP5 and could run in parallel — but the standing rule is one task at a time, and there is one backend contributor, so they stay sequential.

## 5. Not in P2 — deliberately

- **Issue #32 (control-plane RLS) is a P1 patch, not a P2 checkpoint.** P1's exit criterion already requires unauthorized content be blocked *in SQL*, so this is an unmet P1 gate, not new scope. Same reasoning as F2 → `p1.0.1`. It should ship as **`p1.0.5`** ahead of CP5, because CP5 adds another table that references `principal`.
- **`acl_grant` is unused.** P1 recorded an intent to "evolve clearance-only retrieval to reviewed object-level policy". The table exists and nothing reads it. That is a real decision to make, but it is a retrieval-policy change and the retrieval core is frozen — so it needs measured justification, not a checkpoint slot. Leave it; record it.

## 6. Open questions — answer before CP5 starts

1. **What is "board" in the ROADMAP's object list?** It reads "workspace, member, board, meeting…" as three distinct things. This proposal assumes **board = the board-member directory** (FR-WS-03). The alternative reading is a `board` entity proper, enabling committees — main board, audit committee, remuneration committee — each with its own membership and meetings. That is a materially bigger model and would change CP5's shape and probably CP1's. The PRD does not settle it: §242 lists Workspace as holding members and meetings, with no separate Board object. **Owner decision needed.**

2. **Does `decision_stance` migrate to `board_member_id`, and when?** Proposed: add nullable in CP5, backfill separately, make required only once the directory is real. Confirm, or say if the free-text column should simply stay.

3. **`version_no` vs `version` — settle it as a house rule.** Three aggregates now carry both (`version` = optimistic-concurrency counter, `version_no` = published-artifact lineage). It is correct but reads as duplication to every new reader. This should become one line in `CONTRIBUTING.md` rather than being re-explained at each checkpoint. (Raised as #23 §6 Q3 and never answered.)

4. **Does CP8 have a producer in V1?** See above. If not, say so in the decision record and keep it small.

## 7. Rough shape

Five aggregate checkpoints plus an exit gate. On the observed CP1–CP4 cadence — roughly one checkpoint per two to three days with one backend contributor, review included — that is on the order of two to three weeks, assuming the open questions above are answered before CP5 rather than during it.

The estimate is worth little; the sequencing is the point. What would genuinely change the number is question 1: if "board" means committees, CP5 grows and CP1 needs revisiting.
