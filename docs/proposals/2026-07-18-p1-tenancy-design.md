# P1 — Multi-tenancy and security design

**Status:** Design proposal (gates the Meridian scaffolding merge; see issue #5)
**Date:** 2026-07-18
**Owner:** Raghav
**Depends on:** `eval-baseline-v3` (frozen research core, `master`)
**Scope:** How Meridian isolates one customer's board data from another's across **both**
stores, composed with the existing clearance RBAC, **without weakening the frozen core**.

---

## 1. Problem

Callosum today is **single-tenant**. There is no `workspace_id` anywhere. All access control
is *clearance within one organization*: a `principal` has one `clearance` (0 public → 4
restricted), and every read is gated by `object.sensitivity <= clearance`, enforced in the
SQL `WHERE` clause (`vector_search`) and the Cypher path gate (`graph_search`).

Meridian is B2B multi-tenant: every customer company is a **workspace**, and no query,
embedding, graph path, quote, or even *count* may cross a workspace boundary. Postgres RLS
covers the relational/vector half; **Neo4j has no RLS**, so the graph half needs explicit
query-level scoping. Both must compose with clearance, both must fail closed, and the frozen
retrieval algorithm must not change its ranking behavior.

## 2. The invariant (north star)

> A principal `P` acting in workspace `W` may read object `O` **iff**
> `O.workspace_id = W` **AND** ( `O.sensitivity <= P.clearance_in(W)` **OR** an in-workspace
> `acl_grant(P, O)` exists ).

Two independent, fail-closed gates: **tenant isolation (outer)** and **clearance (inner)**.
Neither may widen the other. Tenant isolation is checked *first and everywhere* — in SQL, in
Cypher, in the withheld-count query, in multi-hop traversal, and in the audit log.

## 3. Postgres design

### 3.1 New objects

```sql
CREATE TABLE workspace (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT NOT NULL,
    external_id TEXT UNIQUE,          -- maps to the auth provider's org id (Kinde org)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Clearance becomes per-workspace: a founder is clearance 4 in their own workspace but may
-- sit as an observer (clearance 1) on another company's board. So clearance moves OFF
-- principal and ONTO the membership edge.
CREATE TABLE membership (
    principal_id UUID NOT NULL REFERENCES principal(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
    role         TEXT NOT NULL,       -- founder | admin | exec | director | observer | advisor
    clearance    INT  NOT NULL REFERENCES sensitivity(level),
    active       BOOLEAN NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (principal_id, workspace_id)
);
```

`principal.clearance` and `principal.org` are **deprecated** in favor of `membership`
(kept nullable during migration, dropped after). `principal` becomes a global identity;
authorization is always workspace-scoped.

### 3.2 `workspace_id` on every tenant-owned table

Add `workspace_id UUID NOT NULL REFERENCES workspace(id)` to: `document`, `chunk`,
`node_version`, `proposed_change`, `extraction_failure`, `query_log`, `acl_grant`.
`chunk.workspace_id` is **denormalized from `document`** — exactly like `chunk.sensitivity`
already is — so the hot retrieval path stays a single-table predicate. Index every
`workspace_id`; make the vector index and sensitivity index composite where it helps
(`(workspace_id, sensitivity)`).

### 3.3 Row-Level Security (the enforcement, not the frozen query)

```sql
ALTER TABLE document        ENABLE ROW LEVEL SECURITY;
ALTER TABLE document        FORCE  ROW LEVEL SECURITY;   -- applies even to the table owner
CREATE POLICY ws_isolation ON document
    USING (workspace_id = current_setting('app.workspace_id')::uuid);
-- repeat for chunk, node_version, proposed_change, extraction_failure, query_log, acl_grant
```

The API sets the tenant context once per request/transaction:

```sql
SET LOCAL app.workspace_id = '<the authenticated workspace>';
```

**Why this matters for the freeze:** with RLS active and `app.workspace_id` set on the
connection, the frozen `vector_search` SQL — `WHERE c.sensitivity <= %s` — **does not change
at all**. RLS transparently adds `AND workspace_id = current_setting(...)` underneath it. The
clearance predicate stays byte-identical; tenancy is enforced by the policy + the connection
setting. The only code change is in the **connection layer** (`store.py::pg()`), which is
infrastructure, not the retrieval algorithm.

`FORCE ROW LEVEL SECURITY` + a non-superuser app role means a forgotten `SET` yields **zero
rows** (fail-closed), never a cross-tenant leak.

## 4. Neo4j design (no RLS — explicit scoping)

### 4.1 Model: `workspace_id` property + mandatory predicate

Every `(:Entity)` and `(:Chunk)` node carries a `workspace_id` property. Every query adds a
workspace predicate. This extends the two frozen Cypher touchpoints:

**Seed match** (in `graph_search`): scope seeds to the workspace.
```cypher
MATCH (seed:Entity)
WHERE seed.name IN $names AND seed.workspace_id = $workspace_id
```

**Path gate** (the `readable_edges == edge_count` count): extend the readability test so an
edge counts as readable only if its source chunk is **both** in-workspace **and** in-clearance.
```cypher
OPTIONAL MATCH (src:Chunk {id: r.chunk_id})
...
sum(CASE WHEN src IS NOT NULL
          AND src.workspace_id = $workspace_id
          AND src.sensitivity <= $clearance
         THEN 1 ELSE 0 END)  AS readable_edges
WHERE readable_edges = edge_count
```

A cross-workspace or missing chunk drops `readable_edges` below `edge_count`, so the whole
path fails closed — the exact mechanism clearance already uses. Multi-hop traversal therefore
cannot walk out of a workspace even one edge.

### 4.2 Why property-scoping now, database-per-tenant later

Neo4j Community allows a single database, so **database-per-tenant** (the strongest isolation)
needs Enterprise. For the pilot, property + mandatory-predicate scoping is the pragmatic
choice; the isolation guarantee then rests on *every query carrying the predicate*, which we
enforce with (a) a single `graph_search` chokepoint — no ad-hoc Cypher elsewhere — and (b)
per-tenant negative tests (§7). Database-per-tenant is the documented enterprise-hardening
path, not a V1 requirement.

## 5. Frozen-core impact and the exception justification

The Cypher change in §4.1 touches `graph_search`, which is inside the frozen core, so it goes
through the `CONTRIBUTING.md` exception process. The justification is a **safety tightening,
not an algorithm change**:

- The new predicates can only **remove** rows, never add or reorder — ranking is untouched.
- On the existing single-tenant benchmark, **every node shares one `workspace_id`**, so the
  predicate is a tautology and the results are identical. Re-running `callosum eval` against
  `eval-baseline-v3` after the change must reproduce its metrics **exactly** (candidate recall
  100%, grounding 17/21, traversal 100%). That reproduction is the exception's evidence: the
  isolation gate is provably a no-op on single-tenant data and only bites across tenants.
- Postgres needs **no** frozen-query change at all (RLS is transparent, §3.3).

## 6. Auth and request binding (Kinde)

- **Kinde** issues a JWT carrying the user and their **organization** (Kinde orgs = our
  workspaces). Defer SAML SSO + SCIM (issue #5) — Kinde free-tier orgs cover the pilot.
- FastAPI dependency per request: verify JWT → resolve `principal` (by email/sub) → resolve
  `workspace` (`workspace.external_id = kinde_org`) → load the `membership` row → obtain
  `clearance_in(W)`. Reject if no active membership.
- Bind the context: open the Postgres connection, `SET LOCAL app.workspace_id`, and pass
  `workspace_id` + `clearance` into every `graph_search`/`vector_search` call. A request with
  no resolved workspace never reaches the stores.

## 7. Threat model and required per-tenant RBAC negative tests

Every existing clearance negative test gets a **cross-tenant twin**. A principal with full
clearance **in workspace A** attempting to read **workspace B** must get nothing, at every
layer:

| # | Attack | Must be blocked by |
|---|---|---|
| T1 | Vector hit on B's chunk | RLS on `chunk` (returns 0 rows) |
| T2 | Withheld-**count** leak (learning B has *n* secret docs) | RLS applies to the `sensitivity > clearance` count query too — count is 0 |
| T3 | Graph seed match on B's entity | `seed.workspace_id = $workspace_id` |
| T4 | Multi-hop path crossing A→B | path gate: cross-workspace edge drops `readable_edges` |
| T5 | Quote leak via an approved B edge | source `Chunk.workspace_id` check in the gate |
| T6 | `fetch_chunks` by known B chunk id | RLS on `chunk` |
| T7 | ACL escape hatch granting cross-workspace | `acl_grant.workspace_id` must equal the object's |
| T8 | Audit-log read across tenants | RLS on `query_log` |

Exit requires: cross-tenant reads return zero at SQL, Cypher, count, and traversal; and
`eval-baseline-v3` reproduces exactly (§5).

## 8. Migration (Alembic — new; the repo has none today)

The repo uses raw `psycopg` + a single `schema/postgres.sql`, no migration tool. Add
**Alembic** for the product domain.

1. Create `workspace`; insert one **default workspace** for existing data.
2. Add nullable `workspace_id` to all tenant tables; backfill = default workspace.
3. Create `membership`; backfill from each `principal`'s current `clearance`/`org` into the
   default workspace.
4. `ALTER ... SET NOT NULL`; add indexes; enable + FORCE RLS; create policies.
5. Neo4j backfill: `MATCH (n) WHERE n:Entity OR n:Chunk SET n.workspace_id = $default`.
6. Deprecate `principal.clearance`/`principal.org` (drop in a later migration once code no
   longer reads them).

Every step is reversible; the default-workspace backfill keeps `eval-baseline-v3` reproducible.

## 9. Deferred (explicitly out of P1)

- **SAML SSO + SCIM** — enterprise checkpoint, when a buyer needs it (issue #5).
- **Database-per-tenant Neo4j** — Enterprise hardening; property-scoping suffices for pilot.
- **Object-level `acl_grant` activation in retrieval** — PRD notes it isn't wired yet; P1
  designs the workspace-scoping of the table, activation can follow.

## 10. Open decisions

1. Kinde vs. a lighter own-JWT for the pilot (leaning Kinde for org primitives).
2. One Postgres role per app vs. per-tenant roles (leaning one app role + `SET LOCAL`, simpler
   and sufficient with FORCE RLS).
3. Whether `membership.clearance` needs per-object overrides at V1 or only ladder clearance
   (leaning ladder-only; `acl_grant` covers exceptions).

## 11. Exit criteria (maps to ROADMAP P1)

- [ ] Threat/data-flow model and role matrix reviewed.
- [ ] Unauthorized content blocked in SQL, Cypher, quotes, chunks, counts, logs, API, UI.
- [ ] Per-tenant RBAC negative tests (T1–T8) pass.
- [ ] `eval-baseline-v3` reproduces exactly after the core exception (proves the gate is a
      no-op on single-tenant data).
- [ ] Alembic migration + Neo4j backfill tested with reversal.
- [ ] Transcript/retention policy approved (PRD §17).
