# Architecture Decision Records (ADRs)

Short records of *why* major structural choices were made, so the reasoning survives
past the session that made it. Format per record: Decision · Alternatives · Why · Status.
Status is **Accepted** (implemented + in `master`) or **Proposed** (design-only, not built).

---

## ADR-001 — Two stores bridged by a shared chunk UUID
**Decision:** Postgres (records, vectors, RBAC, versions) + Neo4j (entity graph), joined by
a chunk UUID that Postgres mints and Neo4j reuses as a `(:Chunk)` node id.
**Alternatives:** single Postgres with `pgvector` + recursive CTEs for graph; single graph DB.
**Why:** vector recall and bounded multi-hop reasoning are different access patterns; one
UUID lets a vector hit walk into the graph and a graph hit fetch exact source text. Neither
store does both well alone — this bridge *is* the thesis.
**Status:** Accepted.

## ADR-002 — Tenant isolation via database RLS, not application-only filtering (Postgres)
**Decision:** Postgres Row-Level Security (`ENABLE`+`FORCE`) with a `tenant_isolation` policy
keyed on a session GUC (`app.workspace_id`).
**Alternatives:** add `WHERE workspace_id = ?` in every query (application-only).
**Why:** application-only filtering is one forgotten `WHERE` from a cross-tenant leak. RLS
makes isolation the database's job — fail-closed by default, enforced even for queries that
forget to filter.
**Status:** Accepted.

## ADR-003 — A non-superuser runtime role + two-DSN split
**Decision:** app connects as `callosum_app` (`NOSUPERUSER NOBYPASSRLS`, `postgres_app_dsn`);
migrations/admin use the `callosum` superuser (`postgres_dsn`).
**Alternatives:** run everything as the superuser created by `POSTGRES_USER`.
**Why:** **superusers bypass RLS unconditionally — `FORCE` cannot stop them.** RLS was silently
a no-op until the app stopped connecting as a superuser. This was the single most important
correctness fix in P1.
**Status:** Accepted.

## ADR-004 — Neo4j tenant isolation via entity-identity partitioning + query predicates
**Decision:** `workspace_id` is part of entity identity (`MERGE (e:Entity {name,type,workspace_id})`)
plus a workspace predicate on every graph read (seed gate, `readable_edges` path gate,
`entity_names_for_chunks`).
**Alternatives:** rely only on per-query `WHERE` predicates; per-workspace Neo4j databases
(Enterprise edition).
**Why:** Neo4j Community has no RLS, so isolation is query-level and fragile. A shared entity
node (same name across tenants) can't be fixed by a `WHERE` — the *node* is the leak. Baking
`workspace_id` into identity physically partitions the graph, so a colliding name can never
bridge two tenants; the query predicates are defence-in-depth on top.
**Status:** Accepted.

## ADR-005 — Deterministic frozen evaluation as the acceptance gate
**Decision:** the retrieval eval runs against a **seeded gold graph** (no LLM); the gated
metrics are **candidate recall** and **traversal-given-grounding**. LLM grounding metrics are
recorded but do not gate.
**Alternatives:** end-to-end answer-correctness as the gate.
**Why:** the hosted planner LLM is nondeterministic even at temp 0 (429s, sampling), so answer
text can't be a stable gate. Retrieval metrics are deterministic and are exactly what a schema
change (e.g. RLS) could regress — so they're the honest security/quality gate.
**Status:** Accepted. (A cleaner *split* — deterministic security eval fully separated from the
LLM eval — is Proposed in ADR-008-adjacent work / issue #10.)

## ADR-006 — Verified provenance; the research core is frozen
**Decision:** no graph edge exists without its verbatim evidence quote found in the source;
every write is provenance-stamped; the research engine (`store.py`/`retrieve.py` extraction,
verifier, planner, RBAC) is frozen behind `eval-baseline-v3`.
**Alternatives:** trust extractor output; allow ongoing edits to the core.
**Why:** the contribution is *verified* KG construction, not GraphRAG. Freezing prevents
silent regressions; the only sanctioned exception (tenancy) must reproduce `eval-baseline-v3`
exactly — predicates can only remove rows, so single-tenant behaviour is provably unchanged.
**Status:** Accepted.

## ADR-007 — Alembic for product-domain schema migrations
**Decision:** introduce Alembic (`meridian/migrations/`, single linear chain `0001→0005`) for
all post-freeze schema change; the frozen `schema/postgres.sql` remains the base schema.
**Alternatives:** keep hand-run raw SQL scripts.
**Why:** tenancy needed reversible, ordered, reviewable schema change across many tables; raw
scripts have no ordering or rollback. Alembic keeps one source of truth per table.
**Status:** Accepted.

## ADR-008 — Postgres as single source of truth, Neo4j a rebuildable projection
**Decision (proposed):** make Postgres canonical; `store.approve()` writes Postgres-first, then
projects to Neo4j; add a `rebuild-graph` command that replays approved changes → Neo4j.
**Alternatives:** current dual-write; full CQRS / event-sourcing with a message bus.
**Why:** the graph is already derived from approved `proposed_change` rows and `seed-eval`
already rebuilds deterministically, so this mostly *formalizes* an existing property and makes
graph inconsistency self-healing — **without** a message queue (which would add failure modes
for little V1 gain).
**Status:** Proposed — design-only, tracked in issue #10. Not built. Do not implement before P2
planning and only after evidence justifies it.

## ADR-009 — Authentication is OIDC; the session is an httpOnly signed cookie
**Decision:** authenticate via an external OIDC provider. The result is a server-side
session carried in an **httpOnly, `SameSite=Lax`, signed cookie** — not a bearer token.
**Alternatives:** local password auth (credentials table, hashing, reset flow); magic-link
email; bearer token in `Authorization`.
**Why:** `principal` has no credential column and never has — there is nothing to
authenticate against, so *some* identity system had to be built. OIDC holds no secrets in
this repo, which removes password storage, reset flows and breach surface in one move.
The cookie follows from the deployment shape: the frontend is same-origin Next.js, so a
cookie is simpler *and* keeps the session out of JavaScript's reach. A bearer token earns
its keep only with a non-browser client, and none exists — adding one now would be paying
for a consumer we do not have.
**Status:** Accepted (P3, owner-approved 2026-07-29). Not yet built — CP-A.

## ADR-010 — OIDC subject → principal via a separate `principal_identity` table
**Decision:** a new table keying `(provider, subject)` UNIQUE → `principal_id`. **Not** a
column on `principal`, and **not** matched on email.
**Alternatives:** an `oidc_subject` column on `principal`; matching the OIDC `email` claim
against `principal.email` (which is already UNIQUE).
**Why:** email is the tempting option and the wrong one — it is mutable, it gets reassigned
between people when someone leaves, and providers do not guarantee it. OIDC identifies by
`(issuer, subject)`, which is stable and opaque, and that is what should be stored. A
separate table earns its place three ways: more than one provider becomes possible, an
identity can be revoked without touching the person record, and `principal` — declared in
the frozen `schema/postgres.sql` — is not reshaped. It is deliberately **not** tenant-scoped
and needs no RLS: identity is global, `membership` is what scopes. It must not be listable
by the runtime role beyond what login requires, because a table mapping people to external
identities is a directory leak if it can be enumerated.
**Status:** Accepted (P3, owner-approved 2026-07-29). Not yet built — CP-A, one migration.

## ADR-011 — An unknown OIDC subject is rejected, never auto-provisioned
**Decision:** a successfully-authenticated subject with no `principal_identity` row is
**refused**. No `principal` is created as a side effect of login.
**Alternatives:** auto-provision a principal with no membership (authenticates, sees
nothing); auto-provision with a default membership.
**Why:** auto-provisioning creates identity records as a side effect of a stranger visiting
a URL, which turns an authentication endpoint into a write endpoint for anyone the provider
will authenticate — and with a public IdP that is potentially anyone. The middle option is
worse than it looks: it accumulates ghost principals that appear in no directory but exist
in the table, and `principal_identity` rows for people who were never invited. Membership is
what grants clearance in this system; an identity with no membership is not a lesser user,
it is a record nobody asked for. Provisioning is an administrative act and stays one.
**Status:** Accepted (P3, owner-approved 2026-07-29). Not yet built — CP-A.

## ADR-012 — Workspace is selected explicitly and re-validated on every request
**Decision:** where a principal holds more than one membership, an explicit selection step
writes the chosen workspace into the session. Every subsequent request re-validates it
against `membership` before use.
**Alternatives:** infer a default (first, most recent, or only membership); accept the
workspace as a request parameter.
**Why:** storing the choice without re-checking it makes the session a cache of an
authorization fact, and a revoked membership would keep working until the session expired —
which is precisely when it must stop. Re-validating per request costs one indexed lookup and
means access ends when the membership does. Inferring a default is a smaller wrong: a
founder who belongs to two boards should never be *guessed* into one of them. Accepting it
from the request is ADR-013's whole subject.
**Status:** Accepted (P3, owner-approved 2026-07-29). Not yet built — CP-A.

## ADR-013 — `workspace_id` and `clearance` are session-derived, enforced by a schema test
**Decision:** neither value may appear as an endpoint input — no path segment, query
parameter, body field or header. Both are derived server-side from the authenticated
session. **Enforced by an automated test that walks the OpenAPI schema and fails if any
endpoint declares either as a request input.**
**Alternatives:** a documented convention plus code review.
**Why:** every domain function takes `workspace_id` and passes it to `store.pg()`, which
sets the `app.workspace_id` GUC that **every RLS policy reads**. The moment a request can
influence that value, RLS is advisory for anyone who can send one —
`GET /api/resolutions?workspace_id=<someone-else's>` would be honoured, because the database
was told to trust the GUC. This is the limitation P2's acceptance record carries forward,
and P3 is where it stops being theoretical.

Convention is the wrong enforcement mechanism for a rule whose violation is invisible in
review: an endpoint that accepts `workspace_id` looks *ordinary*. The schema test makes the
rule mechanical — the same reasoning that made composite `(id, workspace_id)` foreign keys a
standing rule after p1.0.5, and the reason `meridian/tenancy.py` raises rather than
defaulting. Three layers now hold the same line: the guard rejects a missing workspace, the
session is the only source of a present one, and the test proves no endpoint offers a third.
**Status:** Accepted (P3, owner-approved 2026-07-29). Guard built (#67); test not yet built
— CP-A.

## ADR-014 — API endpoints mirror the domain functions 1:1 for P3
**Decision:** each public function in `meridian/*.py` gets one endpoint, shaped as the
function is — `list_resolutions` → `GET /api/resolutions`, `get_resolution` →
`GET /api/resolutions/{id}`, `transition_resolution` →
`POST /api/resolutions/{id}/transition`. **Minus two arguments**: `workspace_id` and
`clearance` are never accepted from the client and are supplied by
`deps.current_principal` from the session (ADR-013). Pure helpers that touch no
database — `resolutions.tally`, `commitments.is_overdue` — get no endpoint at all;
they are computed client-side from data already returned.
**Alternatives:** task-shaped / BFF endpoints composed around screens
(`GET /api/meeting/{id}/prep-pack` returning meeting, agenda, pack and decisions in
one call).
**Why:** the frontend's `lib/*.ts` modules were deliberately written to mirror the
Python dataclasses field-for-field, so a 1:1 API makes each swap a change of transport
and nothing else — six of them become mechanical, and the existing frontend tests
become the acceptance criteria without being rewritten. It is also the reviewable
option: a reviewer can check an endpoint against one function rather than against a
composition whose behaviour lives in the endpoint itself.

**The cost, stated rather than discovered later:** 1:1 leaks the domain model into the
wire format, so a domain refactor becomes a breaking API change, and a screen needing
four aggregates makes four round trips. Both are real. Neither bites at P3's scale —
one frontend, same origin, no external consumers — and paying for a BFF layer before
any real flow exists would be designing against imagined screens.
**Revisit at P6**, when live meeting flows exist and the round-trip cost is measurable
rather than assumed. That is the point at which composition should be evidence-driven,
in keeping with the standing rule that structure follows measurement.
**Status:** Accepted (P3, owner-approved 2026-07-29). Not yet built — CP-B onward.

## ADR-015 — Minutes are workspace-scoped by design (Option 1)
**Decision:** `minutes` records are scoped by `workspace_id` (Postgres RLS) and carry no `sensitivity` column or `clearance` parameter.
**Alternatives:** Add coarse `sensitivity` level to `minutes`; derive clearance from meeting or board pack items.
**Why:** Minutes document formal board conclusions in high-level prose. A single `sensitivity` level for an entire minutes body would create a coarse classification trap — hiding routine resolutions (e.g. approving bank signatories) from an investor-clearance reader just because one paragraph mentions a sensitive topic. Sensitive raw source materials remain strictly clearance-filtered in `board_pack_item`.
**Status:** Accepted (Option 1, resolved in issue #49).


## ADR-016 — The dedup existence oracle is accepted, and made detectable
**Decision:** `intake_document`'s deduplication pre-check stays clearance-blind. A caller
who submits content already filed in their workspace receives `409` whether or not they
could have read the existing document. The oracle is **accepted** rather than closed, and
**every** duplicate refusal — hidden or not — is recorded as an
`intake_duplicate_refused` audit event.

**The leak, stated plainly.** Dedup is content-addressed and per-workspace
(`uq_document_workspace_content_hash`, migration `0022`). Submitting bytes therefore
answers the question "does this workspace already hold this?" for any caller at any
clearance. P4's exit criterion names *hints*, and this is one: a clearance-1 observer who
obtains a leaked memo can paste it into intake and have the board's possession of it
confirmed — corroborating the leak without reading anything they did not already have.

**Alternatives, and why each was rejected:**

- **Add `AND sensitivity <= %s` to the pre-check.** Does not work. The pre-check then
  passes, the INSERT hits the unique index, and the `UniqueViolation` handler raises the
  same `DuplicateDocumentError` one step later. The oracle is a property of
  content-addressed dedup, not of where the predicate sits.
- **Answer as if the intake succeeded.** Closes the oracle by lying. Returning `201` for a
  document that was not filed reports an event that did not happen, which `rules.md` §2
  forbids, and any client trusting the `201` is corrupted. Returning the *existing*
  document's id would disclose more than the `409` did.
- **File a second row at the caller's level.** Requires dropping the per-workspace hash
  uniqueness `0022` just established, and it is **incoherent with the id scheme**: chunk
  and document ids derive from `uuid5(namespace, workspace:content_hash[:ordinal])`, so
  two rows with the same content in the same workspace produce *identical* ids and would
  `MERGE` onto the same Neo4j bridge nodes. Verified, not assumed. Making this option work
  means redesigning the derivation that gives intake its replay-safety.
- **Accept silently.** Defensible on impact — the caller must already possess the exact
  bytes — but it leaves a known disclosure undocumented, which is the state this ADR
  exists to end.

**Why accept-and-detect.** The disclosure is real but bounded: it is confirmation, not
content, and it requires the caller to hold the exact bytes already. Every way of removing
it costs more than it saves — a lie on the wire, or a schema redesign that breaks
replay-safety. What was missing was not a fix but a decision, and a way to notice the
oracle being used. This product already has an append-only audit trail; "detectable rather
than prevented" is a posture it can actually support.

**Every refusal is audited, not only the hidden ones.** If a row appeared only when the
collision was above the actor's clearance, the *presence* of the row would be the
disclosure, and the audit trail would become a second copy of the oracle for whoever can
read it. The payload carries `actor_could_read` instead. The race path — where the unique
index rather than the pre-check produces the `409` — is audited too, because the caller
learns the identical fact there.

**Depends on D7.** `aggregate_id` is the existing document's id: the correct aggregate, and
also the identifier the oracle would disclose. There is no audit read endpoint today. If
one is built, it must be clearance-aware, or it hands back exactly what the refusal
withheld.

**Cost, stated rather than discovered later.** Intake now writes on a refusal path, so a
duplicate submission costs one extra round trip and a row. A workspace whose users
frequently resubmit will accumulate audit rows that record no state change.

**Status:** Accepted (P4, resolved in issue #147 finding 1). Revisit if an audit read
endpoint is specified (D7), or if intake ever accepts content the submitter does not
already hold — a URL fetch or an integration pull would remove the "already has the bytes"
bound this decision rests on.
