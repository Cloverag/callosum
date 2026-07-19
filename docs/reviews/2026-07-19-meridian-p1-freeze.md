# Freeze Note — `meridian-p1` product baseline (2026-07-19)

**Tag:** `meridian-p1` (annotated) · **Anchored at:** master merge commit for PR #9
**Supersedes as the working baseline:** nothing — this is the *first* Meridian **product**
baseline. The research baseline `eval-baseline-v3` remains separate, immutable, and untouched.

---

## What this baseline is

`meridian-p1` freezes the tree at the point where **P1 multi-tenancy is complete, merged, and
the product now has a frontend shell**. It is the product-track counterpart to the research-track
`eval-baseline-v3`: same verified retrieval core, now wrapped in fail-closed per-workspace
isolation and a UI.

Contents of the baseline:

- **P1 multi-tenancy (PR #11, merged).** Fail-closed per-workspace isolation across *both* stores:
  - **Postgres:** `workspace`/`membership` tables; `workspace_id` on every tenant table; RLS
    `ENABLE`+`FORCE` with the `tenant_isolation` policy on `app.workspace_id`; two-role split
    (`callosum` superuser for migrations vs `callosum_app` NOSUPERUSER NOBYPASSRLS for runtime,
    because FORCE cannot stop a superuser).
  - **Neo4j (no RLS → query-level):** `workspace_id` baked into entity MERGE identity
    `(name, type, workspace_id)` — a structural partition, not a WHERE filter; reads scoped at
    seed + path level; `Principal.workspace_id` threads it as a Cypher param.
  - **Alembic** migrations `0001`→`0005` under `meridian/migrations/`.
- **Entity-conflict feature (PR #6, merged):** `0005_entity_conflict` + ALIAS_OF, re-parented and
  tenant-scoped.
- **Frontend shell (PR #9, merged):** Next.js application shell + Cinematic Entity Conflict Review
  UI under `frontend/`, built against the Issue #8 mock-API contract, light/dark theming. Entirely
  self-contained in `frontend/` — zero collision with the tenancy work.
- **ADR log** `docs/ARCHITECTURE_DECISIONS.md` (ADR-001..007 Accepted, ADR-008 Proposed).

## Verified state at freeze

- Frozen retrieval core behaviour byte-for-byte reproducible vs `eval-baseline-v3` under a single
  tenant: **candidate recall 21/21, traversal 100%.** (Grounding / 429s are observed-not-gated
  LLM noise, as documented in `findings.md`.)
- Tenant isolation: **70 unit + 8 integration tests** (RBAC + 3 Postgres + 4 Neo4j break-in),
  `tests/test_tenant_isolation.py` + `tests/test_graph_tenant_isolation.py`.
- Frozen-core exception (store.py / retrieve.py / config.py) was invoked for tenancy and is
  justified: predicates only *remove* rows, and the single-tenant path reproduces
  `eval-baseline-v3` exactly.

## Freeze rules

1. `meridian-p1` is immutable and never moves — like the `eval-baseline-v*` tags. All future work
   builds **on** it.
2. master is frozen at this point: **fix only real, reproduced bugs.** No refactors, no speculative
   structure, no churn.
3. **P2 is phased and deliberately unhurried:**
   - *Phase 1* — stabilize; let it sit.
   - *Phase 2* — **measure** where the real complexity / misuse-risk / bugs actually are. Let the
     problems pick the RFC; do not pre-commit to one.
   - *Phase 3* — implement exactly **one** Issue #10 RFC, freeze, verify vs `eval-baseline-v3`,
     then move to the next.
4. RFC ranking (from the Issue #10 comment): 🥇 Neo4j query gateway (collapse tenant-filter
   locations N→1) · 🥈 SET LOCAL txn-scoped RLS (no ctx survives a transaction) · 🥉 split the
   deterministic-retrieval eval from the LLM eval (security validation with zero cloud-LLM
   dependency) · 4️⃣ graph-rebuild command (recreate Neo4j from Postgres on demand). Explicitly
   **not** doing: CQRS, event-sourcing, OPA/Cedar, full-capability auth.

## Relationship to `eval-baseline-v3`

`eval-baseline-v3` freezes the **research** tree (code + M12–16 corpus + gold + eval CSVs) and is
the immutable yardstick every P2 change is verified against. `meridian-p1` freezes the **product**
tree (research core + tenancy + frontend). They diverge only where the accepted frozen-core
exception required it; single-tenant behaviour is identical by construction.
