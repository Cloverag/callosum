# Meridian / Callosum — Decision Log

A human-readable log of the decisions that shaped the project and *why* — the things that aren't obvious from the code or git history. Newest first. Keep entries short; link out for detail.

---

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
