# P2-RFC-001 — Neo4j Query Gateway

**Status:** Proposed · **Design-only — no code changes in this RFC.**
**Date:** 2026-07-20 · **Owner track (A)** · **Depends on:** `meridian-p1.0.1`
**Motivating evidence:** `docs/proposals/2026-07-20-p2-measurement-neo4j-tenant-surface.md` (finding **F2**)

> This is a design document. It specifies the gateway, the migration, and the acceptance bar.
> It changes no code, refactors nothing, and unfreezes nothing.

---

## Goal

Eliminate **Defect Class D-001 — unscoped Neo4j access**: any `session.run()` that reaches entities
or chunks without a `workspace_id` predicate. Do it by making tenant scoping *structural* (impossible
to omit) rather than a per-call-site convention, while keeping retrieval behaviour **byte-identical**
to `eval-baseline-v3`.

## Background

Neo4j has no Row-Level Security, so tenant isolation in the graph is enforced entirely by the query
text. P1 (Brick 3) scoped `store.py` and `retrieve.py` by hand. **F2** (found in the P2 measurement
pass) showed the weakness of that approach: `conflicts.py` (merged via PR #6) introduced its **own**
raw Cypher — outside the files Brick 3 scoped — and it was workspace-blind, cross-pairing entities
across tenants. `meridian-p1.0.1` fixed the *instance* with a minimal patch + regression test.

**This RFC closes the *class*.** The patch proved isolation currently depends on every author
remembering the predicate at every new Cypher site. A whole feature already forgot once. A gateway
makes forgetting structurally impossible for all future access.

## Objectives

- Reduce tenant-filter *authoring points* from **N → 1**.
- Make workspace scoping the **default**, not a convention a caller can skip.
- Preserve all current semantics; **zero** change to retrieval outputs.
- Require **minimal** disturbance to the verified frozen baseline.
- Turn D-001 into an **automatically enforced** rule, not a review guideline.

## Scope

**In scope (evaluate only):** the Neo4j read/write entry points in `store.py`, `retrieve.py`, and
`conflicts.py`.

**Out of scope (do NOT redesign):** retrieval algorithm, planner, grounding, RBAC clearance model,
Postgres RLS, provenance, evaluation. Alembic migrations (schema DDL run as superuser) are not runtime
graph access and are out of scope. The `entity_conflict` UNIQUE-key gap (below) is **explicitly
deferred**.

---

## Deliverable 1 — Current query surface

Every Neo4j entry point (post-`meridian-p1.0.1`; all sites are currently scoped by hand):

| Site | File:line | Kind | Scoped? | Frozen? | Disposition |
|------|-----------|------|---------|---------|-------------|
| `ensure_constraints` | store.py:342 | DDL | n/a | yes | grandfather (allowlist) |
| `entity_names` | store.py:353 | read | ❌ unscoped | yes | **DELETE (F3 — dead code)** |
| `entity_names_for_chunks` | store.py:373 | read | ✅ | yes | grandfather (allowlist) |
| `upsert_chunk_node` | store.py:397 | write | ✅ | yes | grandfather (allowlist) |
| `apply_entity` | store.py:422 | write | ✅ | yes | grandfather (allowlist) |
| `apply_relationship` | store.py:454 | write | ✅ | yes | grandfather (allowlist) |
| `graph_search` | retrieve.py:400 | read | ✅ | yes | grandfather (allowlist) |
| `_entity_mentions` | conflicts.py:56 | read | ✅ (p1.0.1) | **no** | **migrate to gateway now** |
| `_already_known` (ALIAS_OF) | conflicts.py:117 | read | ✅ (p1.0.1) | **no** | **migrate to gateway now** |

Surface = **8 live operations** (after deleting the dead `entity_names`). Small and — because
retrieval is frozen — **not growing**. That is what makes a bounded repository the cheap option.

## Deliverable 2 — Defect analysis

**How F2 happened:** `conflicts.py` opened its own `driver.session()` and wrote Cypher that matched
`(:Chunk)-[:MENTIONS]->(:Entity)` with no `workspace_id` predicate, and matched ALIAS_OF entity
identity on `(name, type)` only. Nothing structurally required the predicate; the reviewer/author
simply had to notice it was missing, and didn't. `detect_conflicts` didn't even accept a workspace
parameter, so there was nothing to thread.

**Remaining D-001 risk after p1.0.1:** the instance is fixed but the *class* is open — the next
feature that opens a `driver.session()` and writes entity/chunk Cypher can reintroduce it, invisibly,
with green tests (there is no test that fails on the mere existence of unscoped raw Cypher). This RFC's
ban-test (Deliverable 4) is what closes that.

## Deliverable 3 — Gateway API proposal *(interface only, no implementation)*

A **bounded repository**: one method per existing query shape — **not** a generic `query(ctx, cypher)`
passthrough (which would only relocate D-001: it hands the caller the workspace param but still trusts
them to write the predicate). Named methods bake the predicate in; callers author **no raw Cypher**.

**Context object** — reuse what exists; invent minimally:
- Reads carry the existing `Principal` (already holds `workspace_id` + `clearance`).
- Writes/scans that have no user carry a tiny `GraphContext(workspace_id: str)`.
- Both expose `.workspace_id`; the gateway injects it into every query as the reserved `$workspace_id`
  param. A method **cannot** be called without a context, so the predicate can never be absent.

Target surface (~8 methods, mirroring Deliverable 1):

```text
# reads
graph.entity_mentions(ctx)                         -> list[dict]      # conflicts scan
graph.alias_edge_exists(ctx, a, b)                 -> bool            # conflicts ALIAS_OF check
graph.entity_names_for_chunks(ctx, chunk_ids)      -> list[str]       # (frozen: grandfathered)
graph.traverse(ctx, seeds, max_hops)               -> (facts, chunks) # (frozen: grandfathered)

# writes
graph.upsert_chunk(ctx, ...)                        -> None            # (frozen: grandfathered)
graph.upsert_entity(ctx, ...)                       -> None            # (frozen: grandfathered)
graph.upsert_relationship(ctx, rel_type, ...)      -> None            # (frozen: grandfathered)

# admin
graph.ensure_constraints()                          -> None            # DDL, no tenant scope
```

**Enforcement properties:**
- Workspace scoping is mandatory and centralized — every read predicate and every write identity gets
  `$workspace_id` from `ctx`, in **one** module.
- **No raw-Cypher entry point exists** on the gateway, so a caller cannot express an unscoped query.
- **Safe structural interpolation is preserved:** `rel_type` stays validated against `RelationType`
  and `max_hops` stays clamped 1–3 inside the gateway (AGENTS.md injection rule) — they remain
  validated structural arguments, never string-formatted caller input.

**Not in this design:** no generic ORM, no query builder, no dynamic label/relationship abstraction,
no caching layer. If the live surface is 8 operations, the gateway is 8 methods.

## Deliverable 4 — Migration plan (smallest safe sequence)

Strangler migration; each step keeps the full suite green.

1. **Red first** — the F2 regression (`test_conflict_scan_cannot_cross_workspace`) already exists and
   is green; add a failing `test_no_raw_cypher_outside_gateway` (see below) to define the end state.
2. **Introduce the gateway module** with the reads/writes `conflicts.py` needs (`entity_mentions`,
   `alias_edge_exists`) — non-frozen, the actual F2 site, lowest risk. Delete dead `entity_names` (F3).
3. **Migrate `conflicts.py`** call sites to the gateway. Run integration (9/9) — behaviour unchanged.
4. **Turn on the ban-test** with the frozen allowlist in place (Deliverable: policy below). It now
   goes green because the only remaining raw `session.run` sites are the allowlisted frozen ones.
5. Frozen sites are **not** migrated now (see policy). Their gateway methods are *specified* here but
   implemented/wired only when the freeze is next lifted for another reason.

## Deliverable 5 — Acceptance criteria

- All **new/non-frozen** Neo4j access flows through the gateway; `conflicts.py` holds no raw Cypher.
- **No raw `session.run()`** outside the gateway module or the explicit frozen allowlist (CI-enforced).
- Dead `entity_names` removed.
- Existing unit + integration tests remain green (integration **9/9** on a clean DB).
- **`eval-baseline-v3` deterministic metrics unchanged** (traversal 100%, ablation 38%→100%, grounding
  17/21, graph-fact recall 100%) — verified because no frozen file was touched.
- F2 regression test still passes.

## Deliverable 6 — Risks

- **Compatibility:** low. Only `conflicts.py` (non-frozen) changes call sites; frozen code untouched,
  so retrieval cannot drift. Risk is confined to the two migrated queries, covered by integration 9/9.
- **Performance:** neutral. The gateway preserves per-call session semantics (same `with
  driver.session()` lifecycle already used); no new round-trips. `detect_conflicts`' per-pair
  `alias_edge_exists` call is unchanged from today.
- **Rollback:** trivial. The change is additive (new module) + a two-site call swap in one non-frozen
  file; revert the commit. The frozen baseline is never in the blast radius.

---

## Policy — grandfather the frozen queries (temporarily)

Frozen query sites are allowlisted **not because they are special, but because they already satisfy
the invariant and are covered by the frozen evaluation baseline.** The rule:

> Existing frozen, verified query sites are explicitly allowlisted. **All new or modified Neo4j access
> must go through the gateway.**

### Technical debt (bounded, not permanent)

> The allowlisted frozen query sites remain **only until the next planned retrieval change**. At that
> point they are migrated into the gateway *before* any additional retrieval work proceeds. The
> allowlist must not become permanent architecture; it is a bridge, and this note is its expiry.

## CI ban-test — D-001 as an enforced rule

`test_no_raw_cypher_outside_gateway` (a source-level security test, per AGENTS.md "treat permission
tests as security tests"):

- greps the tree for `session.run(` and `.session(`;
- **allowed:** the gateway module, and the explicit frozen allowlist (a hardcoded set of
  file:function entries);
- **fail:** any other occurrence.

This turns D-001 from a review guideline into an automatically enforced invariant — a new unscoped
Cypher path fails CI on introduction, not in production.

## F3 — remove while we're here

Delete the dead, unscoped `store.entity_names` (store.py:353): zero callers, but an unscoped
cross-tenant read sitting in the public store API is a footgun (an earlier design wired it into the
planner). Removing it is in-scope cleanup for this RFC.

## Explicitly out of scope

The `entity_conflict` UNIQUE key is `(name_a, type_a, name_b, type_b)` **without** `workspace_id`, so
the same name pair across two tenants collides on one row. Latent until multi-tenant detection runs.
This is a **schema migration**, not a gateway concern — tracked separately, not addressed here.

---

## Decision log (for the eventual implementation checkpoint)

- Repository over passthrough — passthrough relocates D-001, doesn't close it.
- Grandfather-frozen over migrate-all — smallest disturbance to a verified baseline; F2's measured
  need was in non-frozen code.
- Allowlist is temporary, retired at the next retrieval change.
- CI ban-test is the class-level guarantee.

*Design-only. Implementation is a separate, reviewed checkpoint that must meet Deliverable 5.*
