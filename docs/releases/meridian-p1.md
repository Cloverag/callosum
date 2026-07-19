# Meridian P1 — Release Notes

**Tag:** `meridian-p1` (annotated) · **Commit:** `04dfd2f` · **Date:** 2026-07-19
**Research baseline:** `eval-baseline-v3` (immutable; the yardstick every product change is verified against)
**Status:** Frozen. Fix only real, reproduced bugs — no refactors, no churn.

> One-line answer to "what was Meridian P1?": the verified graph+vector RAG research core,
> wrapped in fail-closed per-workspace multi-tenancy across both stores, plus a Next.js
> frontend shell — the first tagged **product** baseline, distinct from the research baseline.

---

## Product capabilities delivered

- **Multi-tenancy — Postgres.** `workspace`/`membership` tables; `workspace_id` on every tenant
  table; Row-Level Security `ENABLE`+`FORCE` with a `tenant_isolation` policy keyed on the
  `app.workspace_id` session GUC. Clearance moved to per-workspace membership.
- **Multi-tenancy — non-superuser runtime role.** Two-role / two-DSN split: `callosum` superuser
  for migrations/admin vs `callosum_app` (NOSUPERUSER NOBYPASSRLS) for runtime — because `FORCE`
  cannot stop a superuser. Runtime connects as `callosum_app` and `SET app.workspace_id`.
- **Multi-tenancy — Neo4j (no RLS → query-level).** `workspace_id` baked into the entity MERGE
  identity `(name, type, workspace_id)` — a *structural* partition, not a WHERE filter (a colliding
  name cannot bridge tenants). Reads scoped at seed + path level; `Principal.workspace_id` threads
  it as a Cypher param.
- **Entity-conflict feature** (`0005_entity_conflict` + ALIAS_OF), re-parented and tenant-scoped.
- **Alembic migrations** `0001`→`0005` under `meridian/migrations/` (the repo previously had none).
- **Frontend shell** — Next.js application shell + Cinematic Entity Conflict Review UI under
  `frontend/`, built against the Issue #8 mock-API contract, light/dark theming. Self-contained;
  wiring real endpoints later is a one-file change (`lib/api.ts`).

## Acceptance metrics

- **Frozen retrieval core, single tenant:** byte-for-byte reproducible vs `eval-baseline-v3` —
  **candidate recall 21/21, traversal 100%.** (Grounding / 429s are observed-not-gated LLM noise,
  per `docs/findings.md`.)
- **Tenant isolation:** 70 unit + 8 integration tests — RBAC + 3 Postgres + 4 Neo4j break-in
  attempts (`tests/test_tenant_isolation.py`, `tests/test_graph_tenant_isolation.py`).
- **Frozen-core exception** (store.py / retrieve.py / config.py) invoked for tenancy and accepted:
  predicates only *remove* rows; the single-tenant path reproduces `eval-baseline-v3` exactly.

## Known limitations

- Tenant filtering is enforced in **N locations** in the Neo4j query layer rather than one gateway
  (→ deferred RFC 🥇). Correct today, but a future query that forgets the predicate is the risk.
- RLS context is set per-connection via `SET`, not per-transaction `SET LOCAL` (→ deferred RFC 🥈).
- The deterministic-retrieval eval and the LLM eval are not yet split, so security validation still
  carries a cloud-LLM dependency (→ deferred RFC 🥉).
- Coreference (M16) and conflict-synthesis (M15) gaps remain from the research track — documented,
  not regressions.

## Deferred RFCs (P2 backlog — Issue #10)

Ranked; P2 implements **exactly one at a time**, then freeze + verify vs `eval-baseline-v3`:

1. 🥇 **Neo4j query gateway** — collapse tenant-filter locations N→1 (no raw Cypher outside it).
2. 🥈 **`SET LOCAL` txn-scoped RLS** — no context survives a transaction.
3. 🥉 **Split deterministic eval from LLM eval** — security validation with zero cloud-LLM dependency.
4. **Graph-rebuild command** — recreate Neo4j from Postgres on demand (ADR-008 direction).

Explicitly **not** doing: CQRS, event-sourcing, OPA/Cedar, full-capability auth.

## References

- **Freeze note:** [`docs/reviews/2026-07-19-meridian-p1-freeze.md`](reviews/2026-07-19-meridian-p1-freeze.md)
- **P1 acceptance:** [`docs/reviews/2026-07-19-brick3-p1-acceptance.md`](reviews/2026-07-19-brick3-p1-acceptance.md)
  · [`docs/reviews/2026-07-19-brick2b-acceptance.md`](reviews/2026-07-19-brick2b-acceptance.md)
- **Neo4j isolation design:** [`docs/proposals/2026-07-19-brick3-neo4j-isolation-design.md`](proposals/2026-07-19-brick3-neo4j-isolation-design.md)
- **ADRs** ([`docs/ARCHITECTURE_DECISIONS.md`](ARCHITECTURE_DECISIONS.md)) — the design reasoning:
  - ADR-001 Two stores bridged by a shared chunk UUID
  - ADR-002 Tenant isolation via database RLS, not application-only filtering (Postgres)
  - ADR-003 A non-superuser runtime role + two-DSN split
  - ADR-004 Neo4j tenant isolation via entity-identity partitioning + query predicates
  - ADR-005 Deterministic frozen evaluation as the acceptance gate
  - ADR-006 Verified provenance; the research core is frozen
  - ADR-007 Alembic for product-domain schema migrations
  - ADR-008 Postgres as single source of truth, Neo4j a rebuildable projection *(Proposed)*
- **Merged PRs:** #11 (P1 tenancy) · #6 (entity_conflict/ALIAS_OF) · #9 (frontend shell)
