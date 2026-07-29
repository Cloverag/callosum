# P3 — implementation roadmap

**Status:** roadmap for review. **Nothing here authorises code** until the maintainer
signs off §7.
**Author:** maintainer · **Date:** 2026-07-29 · **Master:** `c3a74cb`
**Supersedes nothing.** Builds on [the P3 scope](./2026-07-29-p3-scope.md) (#65), which
this document verifies line by line before planning on top of it.

**Decided by the owner, 2026-07-29: authentication is OIDC.** Open question 1 in the
scope doc is closed. The consequences are worked through in §4 and §5.

Checkpoints are named, never numbered by migration. Take the next free slot from
`meridian/migrations/versions/` at implementation time.

---

## 1. Verification of the scope document

Every claim re-checked against `c3a74cb`. Four confirmed, one imprecise, and **four
things the scope document missed** — three of which change the plan.

| Scope claim | Verdict |
|---|---|
| 56 domain functions across `meridian/*.py` | ✅ exactly 56 public functions |
| 2 HTTP endpoints, both `/health` | ✅ confirmed (app exposes 6 routes; 4 are FastAPI built-ins) |
| 0 lines of authentication | ✅ confirmed — no `authlib`, `jose`, or `itsdangerous`; nothing auth-shaped in `meridian/` |
| `store.pg()` sets the `app.workspace_id` GUC every RLS policy reads | ✅ confirmed, `src/callosum/store.py:48-51` |
| `resolve_principal()` JOINs `principal → membership` and fails closed | ✅ confirmed |
| 6 of 10 mocks map to a backend module | ✅ confirmed |
| "Every domain function takes `workspace_id`" | ⚠️ **55 of 56.** `resolutions.tally()` does not, correctly — it is pure and touches no database. The claim is true of every function that reaches Postgres. |

### 1.1 What the scope document missed

**(a) `store.pg(None)` fails OPEN, and `store.py` is frozen.**

```python
(workspace_id or DEFAULT_WORKSPACE_ID,)     # src/callosum/store.py:50
```

A `None` workspace does not raise — it silently becomes the Default Workspace. Under
the CLI that is a convenience. Behind an API it means **any bug that loses the
workspace reads another tenant's data**, and it fails in the direction that looks like
success.

`store.py` is one of the five frozen files, so this default cannot be changed without
an eval-justified exception. **The product layer must therefore never call
`store.pg()` with a possibly-`None` workspace**, and that has to be enforced in
`meridian/`, not wished for. This is the single most important consequence of the
verification pass.

**(b) `resolve_principal()` cannot be the API's identity path.**

```sql
WHERE p.name ILIKE %s ... ORDER BY p.name LIMIT 1     -- with %fragment%
```

A fuzzy substring match returning the first alphabetical hit is a sensible CLI
affordance ("who am I? `raj`") and an unacceptable authentication path: two principals
whose names share a substring resolve to whichever sorts first. OIDC needs lookup by a
**stable, opaque subject**, not by name.

The fail-closed *membership* JOIN in that function is exactly right and must be reused.
It is the name matching that has to go.

**(c) `principal` has no column to key an OIDC subject on.**

```
principal(id, name, email UNIQUE, role, clearance, org, created_at)
```

`email` is unique but is the wrong key: it is mutable, it is re-assignable between
people, and providers do not guarantee it. OIDC identifies by `(issuer, subject)`.
**This requires a migration** — see §6.

**(d) `Principal` is defined in `retrieve.py`, which is frozen.**

`retrieve.ask()` takes that dataclass, so the API constructs a frozen-core type. That
is legitimate — it is the engine's public surface — but **no field can be added to it**.
Anything the API needs to carry beyond `id / name / role / clearance / workspace_id`
lives in a product-side session object that *holds* a `Principal` rather than extending
one.

**(e) Corrected from my own first read:** FastAPI 0.139, uvicorn, starlette, pydantic
and httpx **are** installed and `meridian/api/main.py` imports and serves. `pip show`
reported them missing; importing them proves otherwise. Only `authlib` and
`itsdangerous` are genuinely absent.

---

## 2. Which backend modules become endpoints first

Ordered by **contract stability × frontend readiness**, not by size.

| Order | Module | Functions | Why here |
|---|---|---:|---|
| 1 | `resolutions` | 8 | Newest contract (CP6), 32 integration tests, frontend surface already shipped and mock-shaped to match. Best vertical slice. |
| 2 | `board_members` | 6 | Small, read-heavy, and every other surface needs it to resolve ids to people. |
| 3 | `meetings` | 5 | Root aggregate most others hang off. |
| 4 | `commitments` | 6 | CP7, clean contract, no frontend yet — proves the API can lead the UI. |
| 5 | `packs` | 9 | **Highest-risk read path**: clearance-filtered and position-renumbered server-side. Deliberately late, after the pattern is proven. |
| 6 | `minutes` | 6 | Simple, but blocked on the #49 clearance decision. |
| 7 | `decisions` | 7 | Straightforward; `person_name` → `board_member_id` cleanup rides along. |
| 8 | `agenda` | 6 | Lowest independent value; nothing renders it alone yet. |
| 9 | `audit` | 3 | Read-only surface, and a genuine product question: who may read the trail? |

**`packs` is the one to be careful with.** Its clearance filtering and position
renumbering happen inside the domain function. Over HTTP the response must preserve
both properties, and the existing frontend test asserting "no field a caller could
subtract from" has to keep passing against real data.

---

## 3. Frontend mocks: mechanical, blocked, and undecided

### 3.1 Mechanical — six modules

`board-members`, `decisions`, `meetings`, `minutes`, `packs`, `resolutions`.

Each `lib/*.ts` was written to mirror its Python dataclass field-for-field with
snake_case preserved, precisely so this swap is a change of transport and nothing else.
The work per module is: replace the mock object's methods with `fetch` calls, delete the
mock store, keep every exported type and helper untouched.

**The existing frontend tests are the acceptance criteria.** They assert contract
properties — renumbered positions, no withheld count, advisory tally, inverted lock
sets — and they must pass unchanged against live data. If one fails, the API is wrong,
not the test.

### 3.2 No backend — four modules

| Mock | Reality | Recommendation |
|---|---|---|
| `documents.ts` | `document` is in the frozen core schema; no `meridian/` module | Add a thin product-side read module. Do **not** widen the frozen schema. |
| `graph.ts` | Generated from `GOLD_GROUPS` into a baked layout | **Keep as a demo artifact in P3.** Making it live means per-request Neo4j traversal through the frozen gateway — a performance and scoping project, not a wiring task. Defer to P6. |
| `assistant.ts` | Maps to `retrieve.ask()` — LLM, latency, cost, streaming | **Defer to P6.** It is the only surface that costs money per interaction and the only one needing streaming. |
| `insights.ts` | **No source exists** | Decide tile by tile: derive from a real query or delete the tile. **Never approximate.** |

`insights.ts` has been the site of two data-honesty failures. It should be the *last*
thing wired and the first thing challenged: every tile must name the query behind it.

---

## 4. Architectural decisions that block implementation

**D1 — How is the session carried?** *(blocks everything)*
OIDC is decided; the session that results from it is not. Recommend an **httpOnly,
SameSite=Lax, signed session cookie** (`itsdangerous` via Starlette's
`SessionMiddleware`). Same-origin Next.js makes this simplest and keeps tokens out of
JavaScript. A bearer token only earns its keep with a non-browser client, and none
exists.

**D2 — What links an OIDC subject to a `principal`?** *(blocks CP-A)*
Recommend a new `principal_identity` table: `(provider, subject) UNIQUE → principal_id`.
Not a column on `principal`, for three reasons: it supports more than one provider, it
allows an identity to be revoked without touching the person record, and it avoids
reshaping a table declared in the frozen `schema/postgres.sql`. See §6.

**D3 — What happens on first login for an unknown subject?** *(blocks CP-A)*
Three options: reject (an admin must pre-provision), auto-provision a `principal` with
no membership (they authenticate but see nothing), or auto-provision with a default
membership. **Recommend reject.** Auto-provisioning creates identities as a side effect
of a stranger visiting a URL, and membership is what grants clearance.

**D4 — Where does `workspace_id` come from when a user belongs to several?**
*(blocks CP-A)*
Recommend an explicit workspace-selection step writing the choice into the session,
validated against `membership` on every request. The value must never be readable from
the request itself — see D5.

**D5 — How is "never from the request" enforced, not merely intended?**
Recommend a single `Depends()` that yields an already-scoped connection, plus **a test
that walks the OpenAPI schema and fails if any endpoint declares a `workspace_id` or
`clearance` parameter.** A convention nobody can violate beats a rule everyone must
remember — the same reasoning that made composite FKs the standing rule.

**D6 — 1:1 endpoints or task-shaped?**
Recommend **1:1 with the domain functions for P3.** It is mechanical, reviewable, and
matches the mocks the frontend already has. Revisit at P6, when real flows exist.

**D7 — Who may read the audit trail?** *(blocks the `audit` endpoint only)*
An audit log is exactly the kind of surface that leaks by listing. Not urgent; it gates
the last module in §2.

---

## 5. What can proceed before those decisions

Real work exists that no decision blocks:

1. **The `store.pg(None)` guard.** A product-side helper in `meridian/` that requires a
   workspace and raises rather than defaulting. Pure hardening, independent of auth,
   and it closes finding (a).
2. **Subject-keyed principal lookup in `identity.py`** — a new function reusing the
   fail-closed membership JOIN but keyed on a stable identifier instead of `ILIKE`.
   The shape does not depend on which provider is chosen.
3. **Error taxonomy.** A single mapping from domain exceptions to HTTP status:
   `*NotFound` → 404, `Stale*` → **409**, `*Validation*` → 422, `*Locked*` → 409,
   `PrincipalNotFound` / `ActorNotInWorkspace` → 403. Needed by every endpoint and
   decided by none of D1–D7.
4. **`decisions.ts` staleness.** It still says `board_member_id` is "coming in CP5";
   CP5a shipped it. A frontend-only fix.
5. **The `/commitments` surface** against the merged CP7 contract, still mock-backed.
   It is the last unbuilt P2 surface and follows the pattern three times proven.

---

## 6. Migration impact

P3 is **mostly not a schema phase.** Expected migrations:

| Migration | Purpose | Risk |
|---|---|---|
| `principal_identity` | `(provider, subject) UNIQUE → principal_id`, `ON DELETE CASCADE` | **Low.** New table, no existing data, no RLS needed — identity is global; `membership` is what scopes. |
| *(possible)* session store | Only if sessions are server-side rather than cookie-carried | Avoided entirely if D1 lands on signed cookies. |

**No migration touches an existing table.** `principal` is not altered — that is the
point of D2's separate table. The composite-FK standing rule does not apply, because
`principal_identity` is not tenant-scoped.

**Constraint to carry:** `principal_identity` must **not** be readable by
`callosum_app` beyond what login needs. A table mapping people to external identities
is a directory leak if it is listable.

---

## 7. Checkpoint breakdown and PR sequence

Small PRs, one reviewable idea each. **PR counts are shape, not schedule** — no time
estimates, because I have no measured basis for one.

### CP-A — Identity and session *(blocked on D1–D4)*
| PR | Content |
|---|---|
| A1 | `principal_identity` migration + tests |
| A2 | Subject-keyed lookup in `identity.py`, reusing the membership JOIN |
| A3 | OIDC login/callback/logout; `authlib` + `itsdangerous` added |
| A4 | Workspace selection into the session, validated against `membership` |
| A5 | **The scoped-connection dependency** + the OpenAPI test from D5 |

**Exit:** a request cannot influence which workspace it reads, and a test proves it by
inspecting every declared endpoint.

### CP-B — One vertical slice, read-only
| PR | Content |
|---|---|
| B1 | Error taxonomy (can land before CP-A) |
| B2 | `GET /api/resolutions` + `/{id}`, session-scoped |
| B3 | Frontend `resolutionsApi` → real fetch; **mock deleted**; existing 25 tests pass unchanged |

**Exit:** `/resolutions` renders from Postgres with no mock in the tree.

### CP-C — Remaining mechanical reads
One PR per module in §2 order: `board_members`, `meetings`, `commitments`, `packs`,
`minutes`, `decisions`, `agenda`. Five to seven PRs. **`packs` carries the
clearance-filtering assertions and gets its own review.**

### CP-D — Writes and concurrency
| PR | Content |
|---|---|
| D1 | `POST`/`PATCH` for one aggregate, with `expected_version` → **409** on conflict |
| D2 | The rest, following the pattern |
| D3 | Frontend conflict handling — a 409 must be actionable, not a toast saying "error" |

### CP-E — The four orphans *(needs §3.2 decisions)*
`documents` read module; `insights` tile-by-tile audit; `graph` and `assistant` formally
deferred to P6 with a recorded exception, the way CP9 was.

### CP-F — States, rate limits, observability
Withheld/error/loading states; rate limiting; request tracing. The withheld discipline
already exists in `/packs` and `/memory` and must survive the swap to real data.

### CP-G — Accessibility and keyboard smoke checks

### CP-H — P3 exit gate
Acceptance record, as CP10 was for P2.

---

## 8. Risks

| Risk | Why it matters | Mitigation |
|---|---|---|
| **`store.pg(None)` fails open** | A lost workspace reads the Default Workspace and looks fine | §5.1 guard; never call the frozen helper directly from the API |
| **`workspace_id` leaks into a request** | RLS is advisory the moment it does | D5's OpenAPI test — mechanical, not a review habit |
| **Clearance drifts from `membership`** | Two sources of truth is how RBAC gets bypassed (CP5b unwound exactly this) | Clearance only ever from `resolve_principal()` |
| **`packs` loses its withholding properties over HTTP** | Silent disclosure; the count is the leak | The existing frontend tests must pass unchanged against real data |
| **`insights.ts` gets wired to something approximate** | Third data-honesty failure in the same file | Every tile names its query or is deleted |
| **Mechanism gate regresses** | Would mean the API reached into the engine | Gate stays byte-identical, as it has since CP6 |
| **OIDC provider config in the repo** | Credential leak | Secrets from environment; nothing provider-specific committed |

---

## 9. Frontend / backend dependencies

```
D1–D4 (owner) ──> CP-A ──> CP-B ──> CP-C ──> CP-D ──> CP-F ──> CP-G ──> CP-H
                              │                 ▲
                              └── frontend swap ┘   (per module, follows its endpoint)

independent of all of the above:
  §5.1 store guard · §5.2 subject lookup · §5.3 error taxonomy
  §5.4 decisions.ts staleness · §5.5 /commitments surface
```

The frontend never leads. Each mock is deleted **in the same PR** that proves its
endpoint, so the tree never holds two implementations of one contract.

---

## 10. Decisions requiring maintainer approval before implementation

**D1–D5 were approved by the owner on 2026-07-29** and are now recorded as
**ADR-009 – ADR-013** in [docs/ARCHITECTURE_DECISIONS.md](../ARCHITECTURE_DECISIONS.md),
which is the authoritative statement. The table below is a summary.

| # | Decision | Resolution | ADR | Blocks |
|---|---|---|---|---|
| D1 | Session transport | OIDC; httpOnly `SameSite=Lax` signed cookie, not a bearer token | ADR-009 | everything |
| D2 | OIDC subject → principal link | new `principal_identity` table on `(provider, subject)`; **never matched on email** | ADR-010 | CP-A |
| D3 | Unknown subject on first login | **rejected** — no auto-provisioning; provisioning stays an administrative act | ADR-011 | CP-A |
| D4 | Multi-workspace selection | explicit step, stored in session, **re-validated against `membership` every request** | ADR-012 | CP-A |
| D5 | Enforcement of "never from the request" | scoped-connection dependency **+ a test that walks the OpenAPI schema** and fails if any endpoint declares `workspace_id` or `clearance` | ADR-013 | CP-A |
| D6 | 1:1 vs task-shaped endpoints | **1:1 with the domain functions**, minus `workspace_id`/`clearance` which come from the session; revisit at P6 | ADR-014 | CP-B |
| D7 | Who may read the audit trail | **still open** | — | `audit` endpoint only |
| — | `graph` + `assistant` deferred to P6 | still open — recommend a recorded exception, as CP9 was | — | CP-E |
| — | `insights` tiles | still open — recommend derive or delete, never approximate | — | CP-E |

**§5 is complete** (#67 guard, #68 id-keyed lookup, #69 error taxonomy, #70 `decisions.ts`,
#71 `/commitments`). **CP-A is complete** (#73 A1 · #74 A2 · #75 A3 · #76 A4 · #77 A5).
D6 is approved as ADR-014, so **CP-B is unblocked**. D7 remains open and gates only the
`audit` endpoint.
