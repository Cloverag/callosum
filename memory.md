# Meridian / Callosum — Decision Log

A human-readable log of the decisions that shaped the project and *why* — the things that aren't obvious from the code or git history. Newest first. Keep entries short; link out for detail.

---

### 2026-07-29 — P3 API shape: 1:1 with the domain functions, revisit at P6
Owner approved D6 as **ADR-014**. Each public `meridian/*.py` function gets one
endpoint, **minus `workspace_id` and `clearance`** — those come from the session
(ADR-013), never from the client. Pure helpers (`tally`, `is_overdue`) get no endpoint;
they are computed client-side.
**Why:** the frontend `lib/*.ts` modules already mirror the Python dataclasses
field-for-field, so a 1:1 API makes six of the swaps a change of transport and nothing
else, and the existing frontend tests become the acceptance criteria unrewritten. It is
also the reviewable option — an endpoint can be checked against one function.
**The cost, recorded so it is not rediscovered:** 1:1 leaks the domain model into the
wire format (a domain refactor becomes a breaking API change) and a screen needing four
aggregates makes four round trips. Neither bites at one same-origin frontend with no
external consumers. Revisit at P6 when round-trip cost is measurable rather than
assumed.

### 2026-07-29 — P3 authentication: OIDC, cookie session, no auto-provisioning
Owner approved D1–D5, recorded as **ADR-009 – ADR-013**. Authentication is **OIDC**; the
session is an **httpOnly signed cookie** (same-origin Next.js, so no bearer token). The
subject maps to a principal through a new **`principal_identity`** table on
`(provider, subject)` — **not** on email, which is mutable and gets reassigned between
people. An **unknown subject is rejected**: provisioning is an administrative act, not a
side effect of a stranger visiting a URL. Workspace is **selected explicitly and
re-validated against `membership` on every request**, so access ends when the membership
does rather than when the session expires.
**Why the enforcement matters most:** `workspace_id` and `clearance` are session-derived and
may never appear as endpoint inputs, because `store.pg()` sets the GUC every RLS policy
reads — a request that can influence it makes RLS advisory. That rule is enforced by **a
test walking the OpenAPI schema**, not by convention, because an endpoint accepting
`workspace_id` looks entirely ordinary in review.
**Ownership:** maintainer is backend owner for P3 while Devguru is unavailable, so the phase
does not stall. If he returns before implementation, review the design together and split
checkpoints — but a single owner during implementation, to avoid duplicated architectural work.

### 2026-07-28 — Next.js `frontend/` is the product frontend; the glass prototype is not
The repo has carried two frontends since 24 July: Next.js `frontend/` and the Vite
glassmorphism prototype at `frontendglass/meridian-glass/`. **Decision (owner): the product is
the Next.js app.** The glass prototype is not the path forward and does not get wired to the
P3 API.
**Why:** P3 puts a real authenticated API behind the UI, and wiring two frontends would double
that work for one product. The Next.js app is where the substance already is — 10 routes, the
design system, the CP3/CP4 surfaces, and 96 tests — while the prototype was a look study, last
touched 24 July and never given data, tests, or a11y work.
Left in the tree for now rather than deleted: it is a visual reference, and removing 78 MB of
vendored prototype is a separate, deliberate commit. No further work goes into it.

### 2026-07-22 — Frontend v2: pivot to blue/light "Calm Desk"
The shipped v1 design system (violet-on-zinc, dark-canonical "Situation Room") is superseded by a new color system: **light-mode only, blue `#2563EB` for action, violet `#6D28D9` reserved for Institutional Memory only**, 95% neutral / 5% semantic. Decision: **rebuild the look from scratch, keep the implemented features** (`src/lib/*`, calendar, entity-conflicts). Reference feel = Linear + Stripe + Vercel: premium, calm, built for long sessions.
**Why:** v1 read as generic/"AI slop" and wasn't interactive enough; the owner wants earned executive trust through hierarchy and elevation, not decoration or extra color. v1 is kept on its branch as a rollback baseline.
Also settled: no dark mode; the AI assistant is a **persistent collapsible right rail**, not a modal.

### 2026-07-21 — Ownership swap: maintainer→frontend, Devguru→backend
Full track swap. The maintainer now owns the frontend (design system, pages, product integration); Devguru owns the backend (domain model, migrations, RLS/tenancy, API contracts, tests, infra).
**Why:** the frontend is the public face of the FYP/demo and needs sustained design ownership; the backend needs disciplined checkpoint ownership. Backend publishes contracts; frontend consumes them (or mocks).

### 2026-07-20 — P2 is measure-first, one step at a time
Rather than pre-committing to an RFC, measure where real complexity/misuse-risk lives, then implement exactly one item, freeze, and verify. This produced the Neo4j query gateway (defect class **D-001**: unscoped Neo4j access) as the evidence-backed first RFC.
**Why:** don't break the "evidence decides priorities" rule on the first release after freeze.

### 2026-07-19 — P1 tenancy: RLS over app-side filtering; split DB roles
Postgres isolation uses RLS `ENABLE`+`FORCE` with a **non-superuser `callosum_app`** runtime role, because superusers bypass RLS unconditionally (FORCE can't stop them). Neo4j has no RLS, so `workspace_id` is baked into entity MERGE identity — a structural partition a `WHERE` clause can't substitute for.
**Why:** fail-closed isolation must hold even against a bug in application code.

### 2026-07-15 — Renamed Meridian → Callosum
The engine is **Callosum** (corpus callosum = the bridge between two hemispheres = graph + vector). "Meridian" now names only the product spec and the fictional demo company.

### (ongoing) — The frozen core is never edited for features
All product work builds *on* the frozen research baseline, never inside it. Tenancy predicates are the one exception, and only ever remove rows.
**Why:** the verified-retrieval result is the research contribution; churn would invalidate the eval baseline.

---

> Note: this is the project's shared decision log. It is distinct from any agent's private working memory.
