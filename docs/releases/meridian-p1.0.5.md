# Meridian P1.0.5 — Release Notes (tenancy release)

**Tag:** `meridian-p1.0.5` (annotated) · **Anchored at:** master after PRs #38, #42, #43
**Date:** 2026-07-28 · **Type:** tenant-isolation release · **Version:** `0.1.5`
**Research baseline:** `eval-baseline-v3` (unchanged)
**Migrations:** `0011_control_plane_rls`, `0012_board_member`, `0013_principal_rls`

> Three changes that only make sense together: the control plane gets row-level security,
> cross-workspace foreign-key references become impossible, and clearance finally resolves
> through `membership` — which is what allowed `principal` itself to be scoped.

## Scope note

This release is broader than the `p1.0.x` name suggests. `0011` is a P1 patch — an unmet P1
exit criterion. `0012` and `0013` arrive with P2 checkpoints CP5a and CP5b.

They are released together deliberately: `0011` could not scope `principal`, because a
membership-derived policy over an empty `membership` table hides every row. `0013` is what
makes `0011` complete. Splitting them across two tags would have published a known,
documented half-fix as a finished one.

**Contents**

| Migration | Change | Origin |
|---|---|---|
| `0011_control_plane_rls` | RLS on `membership` + `workspace`; write grants revoked incl. `sensitivity` | #38 (issue #32) |
| `0012_board_member` | BoardMember directory; **composite FK** so cross-workspace references are impossible | #42 (CP5a, issue #39) |
| `0013_principal_rls` | Clearance resolves through `membership`; `principal` scoped and writes revoked | #43 (CP5b, issue #40) |

---

## Part 1 — control-plane RLS (`0011`)

> Closes an **unmet P1 exit criterion**, not new P2 scope. Four control-plane tables shipped
> with no row-level security while the runtime role held full DML on all of them.

## Why this patch exists

P1's exit criterion requires that unauthorized content be blocked **in SQL**. Every *content*
table satisfies it — all thirteen carry `ENABLE` + `FORCE` + a tenant policy, and the isolation
tests prove it. The **control plane** did not.

`workspace`, `membership`, `principal` and `sensitivity` had no RLS, and `callosum_app` — the
deliberately non-superuser runtime role — held `SELECT, INSERT, UPDATE, DELETE` on all four.

Demonstrated with two workspaces, one membership each, read as `callosum_app` scoped to Alpha:

```
  workspace  |    person     |  role   | clearance
-------------+---------------+---------+-----------
 Probe Alpha | Alpha Founder | founder |         4
 Probe Beta  | Beta Founder  | founder |         4     <- other tenant
```

No document text moved. But "who sits on which board, at what clearance" is confidential in a
board-governance product, and the runtime role could also have granted itself membership
anywhere. This is the same class as F2 (`p1.0.1`) and is scoped the same way: an unmet P1 gate
gets a patch release, not a P2 checkpoint.

## What changed

- **Migration `0011_control_plane_rls`.**
  - `membership` — `ENABLE` + `FORCE` + `tenant_isolation`, same predicate as every other tenant
    table.
  - `workspace` — same, keyed on `id` rather than `workspace_id`: a scoped connection sees exactly
    the workspace it is scoped to and cannot enumerate tenant names.
  - `sensitivity` — no RLS. It is a static five-row lookup with no tenant dimension, so a tenant
    predicate would be meaningless. Write grants revoked; nothing at runtime should edit the
    clearance ladder.
  - **Least privilege** — `INSERT, UPDATE, DELETE` revoked from `callosum_app` on all three.
    Membership and workspace changes are administrative and belong on the superuser path.
- **No code change.** Neither `membership`, `workspace` nor `sensitivity` has a runtime reader:
  `grep` finds no SELECT of any of them in `src/callosum/` or `meridian/`. They are written by
  migrations and by tests through the `_admin` superuser control plane, both of which bypass RLS
  by design. Enabling `FORCE` therefore costs nothing.
- **Regression test** `test_control_plane_membership_is_workspace_scoped` in
  `tests/test_tenant_isolation.py`: two workspaces, one membership each, asserting a scoped caller
  sees exactly one — and that an `INSERT` into `membership` raises `InsufficientPrivilege`.

## Part 2 — composite foreign key (`0012`, CP5a)

Postgres validates foreign keys **as the table owner, bypassing row-level security**, so a
single-column `REFERENCES board_member(id)` validates against rows the caller cannot see.
Reproduced: a stance in workspace A successfully referenced a director in workspace B. Same
shape as the `entity_conflict` unique-key defect closed in `p1.0.4` — a constraint operating
*below* the isolation boundary.

`decision_stance.board_member_id` now references the `(id, workspace_id)` pair against a
`UNIQUE (id, workspace_id)` on `board_member`. The reproduction fails with
`ForeignKeyViolation` **even through the superuser connection**, which is what proves the
constraint rather than the policy is enforcing it — and the regression test asserts it that
way for the same reason.

`ON DELETE RESTRICT` rather than `SET NULL`: `decision_stance.workspace_id` is `NOT NULL`, so
a composite `SET NULL` would try to null it and fail. RESTRICT also matches the
deactivate-never-delete rule.

**Scope was held to this one relationship.** Whether the other nine tenant-scoped FKs should
follow is issue **#41**, for a dedicated migration with a full impact review — the `ON DELETE`
semantics differ per relationship and cannot be changed mechanically.

## Part 3 — clearance through membership (`0013`, CP5b)

The finding that shaped this release: **P1 moved clearance onto a per-workspace `membership`
row and the runtime never adopted it.** Every caller lookup read `principal.clearance`,
`membership` sat empty with no readers, and nothing ever created a membership row.

- `callosum init` moved onto the **admin connection** — it was running as `callosum_app`, and
  could only write `principal` because that table had no RLS and full write grants.
- `init` now seeds `membership` for every principal in the Default Workspace.
- New non-frozen `callosum/identity.py` resolves callers by joining `principal` to
  `membership`. **Fail-closed:** no active membership here means the principal does not
  resolve at all — not their old global clearance, and not clearance 0.
- `0013` puts `ENABLE` + `FORCE` + a membership-derived policy on `principal` and revokes
  writes, closing the gap `0011` had to leave open.

`principal.clearance` is retained as a deprecated bootstrap seed — it is declared in the
frozen `schema/postgres.sql` and still seeds the membership — and demoted with a
`COMMENT ON COLUMN`, so `\d+ principal` warns the next reader.

**`retrieve.py` is untouched.** It still receives a `Principal` and gates on `.clearance`
exactly as before; only the construction of that object moved.

## What was NOT fixed by `0011` alone — `principal`

Recorded here because it is the reason all three ship together. Resolved by `0013` above.

The correct policy for `principal` is **membership-derived**: a person is visible in a workspace
iff they hold a membership there. It cannot be a `workspace_id` column, because `membership`'s
primary key is `(principal_id, workspace_id)` — one person legitimately belongs to several
workspaces.

That policy cannot be applied yet, because **nothing ever creates a membership row.** `callosum
init` seeds principals and no memberships; no migration backfills them; runtime clearance is read
straight off `principal.clearance` in `cli.py`. A membership-derived policy today would hide every
principal from every caller and break the CLI outright.

This is worth stating plainly: **P1 designed clearance as a per-workspace membership property, and
the runtime never adopted it.** `membership` is an empty table with no readers.

Scoping `principal` therefore requires wiring membership for real — seeding it at bootstrap,
moving `callosum init` onto the admin connection (it is a bootstrap command currently using the
runtime role), and resolving clearance through membership. That is a reviewed change of its own,
and it belongs with **CP5 (issue #36)**, which is precisely about the people model.

**Residual exposure until then:** a runtime caller can enumerate the global person directory —
names, emails, roles, clearance values. It can no longer learn *which workspace* any of them
belong to, which was the demonstrated leak.

## Honest bounds

Worth repeating from the issue, because it would be easy to over-read this patch:

`callosum_app` can set `app.workspace_id` to any value — it is an ordinary GUC. RLS throughout
this system is therefore a guardrail against **application bugs**, not a hard boundary against a
compromised runtime role. This patch does not change that, and should not be described as if it
did. What it closes is a cross-tenant *enumeration* path that required no bug at all to exploit.

## Verification

Run on a **clean volume** — `docker compose down -v`, then the full `0001` → `0013` chain — so
it exercises the migration path a new deployment takes, not an incrementally-patched local
database.

| Gate | Result |
|---|---|
| Migrations applied from empty | **13**, `0001` → `0013` |
| Full gated suite (`CALLOSUM_RUN_INTEGRATION=1 pytest`) | **176 passed**, 5 deselected |
| **Mechanism gate** | **PASSED** — candidate 22/22, traversal 21/21 (100%), RBAC fail-closed 1/1 |
| `eval/mechanism.csv` | **byte-identical** to the previous deterministic run |
| Migration up / down / re-up | clean at each of `0011`, `0012`, `0013` |
| Control-plane leak probe | scoped caller sees **1 of 2** workspaces |
| Cross-workspace FK probe | `ForeignKeyViolation`, including as superuser |
| `INSERT INTO membership` / `principal` as `callosum_app` | `permission denied` |
| `callosum init` | runs end to end; 3 principals, 3 memberships |
| Frozen core | untouched — no file in the frozen list changed |

**The byte-identical mechanism run is the load-bearing evidence.** `0013` reroutes how
clearance is resolved, and clearance is the input to the frozen RBAC gate in `retrieve.py`. An
unchanged deterministic tier across all three migrations is what shows the reroute changed
authorization's *plumbing* and not its *behaviour*.

## Honest bounds

Two, both worth not forgetting:

`callosum_app` can set `app.workspace_id` to any value — it is an ordinary GUC. RLS throughout
this system remains a guardrail against **application bugs**, not a hard boundary against a
compromised runtime role. What this release closes are enumeration and cross-reference paths
that required no bug at all.

The composite-FK protection covers **one** relationship. The other nine tenant-scoped foreign
keys still rely on an RLS-scoped existence check in the domain module — a real defence, but by
convention rather than construction. Tracked in #41.
