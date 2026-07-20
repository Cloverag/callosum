# Meridian P1.0.4 — Release Notes (schema patch)

**Tag:** `meridian-p1.0.4` (annotated) · **Anchored at:** master merge of `feat/entity-conflict-workspace-uq`
**Date:** 2026-07-20 · **Type:** tenant-isolation schema patch on `meridian-p1` · **Version:** `0.1.4`
**Research baseline:** `eval-baseline-v3` (unchanged) · **Migration:** `0006_conflict_workspace_uq`

> A one-migration schema patch that closes a **latent cross-tenant collision** in the
> `entity_conflict` table. No code change, no user-visible change, no frozen-core change.

## Why this patch exists

The `entity_conflict` unique key from migration 0005 was `(name_a, type_a, name_b, type_b)`. A
unique key is enforced by an index that sees **every** row — *below* Row-Level Security. So the
same conflict pair proposed in a second workspace collided with the first tenant's row: workspace
B could be refused an insert because workspace A already held that pair, even though neither can
see the other's rows. It was **latent** (detection currently runs default-workspace only) but a
real isolation defect the moment detection becomes multi-tenant. Documented as out-of-scope in
`meridian-p1.0.1` / `p1.0.2`; this closes it.

## What changed

- **Migration `0006_conflict_workspace_uq`** — drops the 0005 auto-named unique constraint and
  adds `uq_entity_conflict_workspace_names UNIQUE (workspace_id, name_a, type_a, name_b, type_b)`.
  Conflict identity and collisions are now **per-workspace**, matching every other tenant table.
- **No code change.** Detection already stamps `workspace_id` explicitly (F2 / `meridian-p1.0.1`),
  so the widened key is satisfied by existing inserts.
- **Regression test** (`tests/test_tenant_isolation.py`) — proves both directions: the same pair
  is allowed across two workspaces, and a duplicate within one workspace is rejected.

## Verification

- **Fresh-volume migration** `0001 → … → 0006` applied cleanly (both stores healthy).
- **Reversible**: upgrade → downgrade → re-upgrade returns the correct constraint each way.
- **Integration 10/10** (`CALLOSUM_RUN_INTEGRATION=1 pytest -m integration`, clean DB) — the 9
  prior tests plus the new cross-workspace regression.
- **Fast suite 78 passed.**
- **Mechanism gate PASSED** (`meridian-p1.0.3`): candidate 22/22, traversal 21/21 (100%), RBAC 1/1
  — a schema constraint change does not perturb the deterministic retrieval mechanism, confirmed.
- **No frozen file touched**; `schema/postgres.sql` untouched (`entity_conflict` lives only in Alembic).

## Note from the build

The first revision id (`0006_entity_conflict_workspace_uq`, 33 chars) overflowed
`alembic_version.version_num` (`varchar(32)`); the migration rolled back transactionally and the
regression test caught it immediately (still-old constraint → cross-workspace collision). Shortened
to `0006_conflict_workspace_uq` (26). A test that fails loudly beats a half-applied schema.

## Status

Re-frozen at `meridian-p1.0.4`. Release line: `meridian-p1` → `p1.0.1` (F2) → `p1.0.2` (gateway) →
`p1.0.3` (mechanism gate) → `p1.0.4` (workspace-scoped conflict key). The p1 tenant-isolation
hardening line is now complete on both stores. **Next: ROADMAP P2 — durable product domain +
migrations** (workspace/meeting/agenda/decision model), the first genuine product-forward
checkpoint since P1.
