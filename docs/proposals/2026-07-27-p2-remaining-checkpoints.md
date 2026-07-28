# P2 — plan for the remaining checkpoints (CP5–CP9 + exit gate)

**Status:** proposal, design-only. Nothing here authorises code.
**Author:** maintainer · **Date:** 2026-07-27 · **Master at time of writing:** `c158086`

---

> ## ⚠ THE MIGRATION NUMBERS BELOW ARE WRONG. DO NOT COPY THEM.
>
> Every slot this document names has been taken by something else. Read the next
> free slot from `meridian/migrations/versions/`, never from a spec.
>
> | This doc says | Actually shipped as |
> |---|---|
> | CP5 `0011_board_member` | **CP5a `0012_board_member`** + **CP5b `0013_principal_rls`** (`0011` went to the control-plane RLS patch, #38) |
> | CP6 `0012_resolution` | **`0014_resolution`** |
> | CP7 `0013_commitment` | **`0015_commitment`** |
> | CP8 `0014_audit_event` | `0014` **is taken** — next free slot is `0016` |
> | CP9 `0015_notification` | `0015` **is taken** |
>
> This is the same failure that produced the CP3/CP4 collision: issue #21 pinned
> `0009_board_pack`, CP4 took `0009` first, and CP3 had to become `0010`. The chain
> survived both times because Alembic linearises on `down_revision`, not on the
> number in the name — but a spec that names a slot weeks before anyone implements
> it will always be overtaken. The design content below is still current; only the
> numbering is stale.

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
| **board** | ⛔ not an aggregate | resolved to BoardMember — see §6 |
| **resolution** | ❌ | — |
| **commitment** | ❌ | — |
| **notification** | ❌ | — |
| **audit** | ❌ | — |

P2 does not end when CP3 merges. Four object families remain to build, plus an exit criterion no aggregate checkpoint covers: *"migration/recovery plan is tested."*

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

### CP8 — Audit event (`0014_audit_event`)

PRD §251: actor, action, target, previous/current state where appropriate, time, request/integration result.

Ahead of Notification deliberately. Audit is what every later feature reads from, and Notification is the one checkpoint that might legitimately be deferred out of V1 — if audit sat last, a deferred Notification would take audit with it.

**Must reconcile with what exists rather than duplicate it.** `query_log` already satisfies FR-MEM-09 (principal, plan, hits, denied count, answer, latency) and is the *retrieval* audit. `audit_event` is the *domain* audit — membership changes, publication, supersession, delivery confirmation. Two tables with clear, documented remits is right; one table trying to be both is not.

**The one place "one aggregate per checkpoint" breaks down.** The table is small; the work is retrofitting CP1–CP7 to emit events, which means touching five already-merged, already-accepted modules in a single diff. That needs deciding up front: either CP8 ships the table plus a write path and each module's emit lands as its own small follow-up commit, or CP8 is explicitly a cross-cutting checkpoint reviewed differently from the aggregate ones. Recommended: the former, so no accepted module is modified without its own reviewable diff.

### CP9 — Notification (`0015_notification`)

FR-EXEC-04: owners are notified of due, overdue, changed and blocked commitments, and recipients can see *why* they received it and which decision originated it.

Scope: `notification` (recipient, kind, subject reference, reason, originating decision, state, attempts, last_error). Channels, templates and sending are P8.

This is the checkpoint most at risk of being over-built, and the only one that is a legitimate candidate for deferral out of P2 entirely. If the answer to "what actually creates a notification in V1?" is "nothing yet, P8 does", then the honest options are a small table with a clean state machine and no producer, or an explicit deferral recorded with an owner and due checkpoint per the ROADMAP operating rule. Both are defensible; padding it out is not.

### CP10 — P2 exit gate (no migration)

The exit criterion no aggregate covers: *"migration/recovery plan is tested."*

Scope: a documented and **executed** restore drill — fresh volume, `0001` → head, seed, verify; a full downgrade/upgrade cycle across the whole chain, not just the newest link; the P2 acceptance record; and a ROADMAP progress update. CP1–CP4 each verified their own migration in isolation; nobody has yet proven the chain restores end to end.

## 4. Sequence and dependencies

```
CP3 (in review) ──> CP5 board_member ──┬──> CP6 resolution ──┐
                                       └──> CP7 commitment ──┴──> CP8 audit ──> CP9 notification ──> CP10 exit gate
```

CP6 and CP7 both depend only on CP5 and could run in parallel — but the standing rule is one task at a time, and there is one backend contributor, so they stay sequential.

CP9 is the only checkpoint whose removal does not break the chain. That is why audit precedes it.

## 5. Not in P2 — deliberately

- **Issue #32 (control-plane RLS) is a P1 patch, not a P2 checkpoint.** P1's exit criterion already requires unauthorized content be blocked *in SQL*, so this is an unmet P1 gate, not new scope. Same reasoning as F2 → `p1.0.1`. It should ship as **`p1.0.5`** ahead of CP5, because CP5 adds another table that references `principal`.
- **`acl_grant` is unused.** P1 recorded an intent to "evolve clearance-only retrieval to reviewed object-level policy". The table exists and nothing reads it. That is a real decision to make, but it is a retrieval-policy change and the retrieval core is frozen — so it needs measured justification, not a checkpoint slot. Leave it; record it.

## 6. DECIDED — no `Board` aggregate in P2 (owner, 2026-07-27)

The ROADMAP's object list reads "workspace, member, board, meeting…", which could have meant a `board` entity proper. **It does not.** The model is:

```
Workspace → BoardMember → Meeting → AgendaItem → Resolution → Commitment
```

- **Workspace** = the organization / tenant.
- **BoardMember** = a governance participant within a workspace, who may have no login.
- **Meeting** keeps `workspace_id` and hangs off the workspace directly. **CP1 is not revisited.**
- BoardMember participates in meetings, votes on resolutions, and owns commitments.

**Rationale:** the PRD models one board per workspace throughout. A `Board` aggregate today adds a foreign key and a migration and unlocks no behaviour.

**Revisit only if a real requirement appears:** multiple boards per workspace (main board, audit committee, risk committee), per-board governance rules, or separate calendars, memberships and permissions. Introducing `Board` later is a migration plus a nullable FK on `meeting` — deliberately left cheap.

## 7. Open questions — answer before CP5 starts

1. **Does `decision_stance` migrate to `board_member_id`, and when?** Proposed: add nullable in CP5, backfill separately, make required only once the directory is populated. Confirm, or say the free-text column simply stays.

2. **`version_no` vs `version` — settle it as a house rule.** Three aggregates now carry both (`version` = optimistic-concurrency counter, `version_no` = published-artifact lineage). It is correct but reads as duplication to every new reader, and should become one line in `CONTRIBUTING.md` rather than being re-explained at each checkpoint. (Raised as #23 §6 Q3, never answered.)

3. **Is CP9 built or deferred?** If nothing produces notifications in V1, a recorded deferral with owner and due checkpoint is the better answer than an empty table.

4. **CP8 shape:** table + write path in the checkpoint, with each module's emit as its own follow-up commit — or one cross-cutting diff? Recommended: the former.

## 8. Rough shape

Five aggregate checkpoints plus an exit gate. On the observed CP1–CP4 cadence — roughly one checkpoint per two to three days with one backend contributor, review included — that is on the order of two to three weeks, assuming the open questions above are answered before CP5 rather than during it.

The estimate is worth little; the sequencing is the point. The Board question that would have moved it most is now settled (§6), so the remaining variance is CP8's retrofit and whether CP9 is built at all.
