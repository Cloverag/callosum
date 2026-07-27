# Meridian P1.0.5 — Release Notes (tenancy patch)

**Tag:** `meridian-p1.0.5` (annotated) · **Anchored at:** master merge of `fix/control-plane-rls`
**Date:** 2026-07-28 · **Type:** tenant-isolation patch on `meridian-p1` · **Version:** `0.1.5`
**Research baseline:** `eval-baseline-v3` (unchanged) · **Migration:** `0011_control_plane_rls`

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

## What this does NOT fix — `principal`

Recorded rather than papered over.

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

| Gate | Result |
|---|---|
| Full gated suite (`CALLOSUM_RUN_INTEGRATION=1 pytest`) | **160 passed**, 5 deselected |
| Migration up / down / re-up | clean, `0010 → 0011 → 0010 → 0011` |
| Leak probe re-run | scoped caller now sees **1 of 2** workspaces |
| `INSERT INTO membership` as `callosum_app` | `permission denied` |
| Frozen core | untouched — no file in the frozen list changed |
| `eval-baseline-v3` | unaffected by construction; no retrieval path touched |

## Migration-chain note

`0011` is consumed by this patch, so **CP5 (BoardMember) becomes `0012_board_member`**. Issue #36
and the P2 plan in #35 are updated accordingly.
