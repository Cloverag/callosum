# Meridian / Callosum — Working Rules

The rules of the road for anyone (human or agent) working in this repo. Authoritative detail lives in the linked docs; this page is the short, enforceable summary. When a rule here and a linked doc disagree, the linked doc wins.

Related: [PRD.md](./PRD.md) · [ROADMAP.md](./ROADMAP.md) · [AGENTS.md](./AGENTS.md) · [CONTRIBUTING.md](./CONTRIBUTING.md) · [docs/architecture.md](./docs/architecture.md) · [docs/ARCHITECTURE_DECISIONS.md](./docs/ARCHITECTURE_DECISIONS.md) · [frontend/DESIGN.md](./frontend/DESIGN.md) · [frontend/PRODUCT.md](./frontend/PRODUCT.md)

## 1. The frozen core is sacred

- The verified retrieval/extraction core (ingest, extract, retrieve, store, schema) is **frozen** at tag `eval-baseline-v3`. Do not edit it to add product features.
- The only sanctioned exceptions are tenancy predicates that *remove* rows (never add), applied brick-by-brick with a failing test first. See [CONTRIBUTING.md](./CONTRIBUTING.md) for the frozen-file list.
- Every change is verified against the frozen eval baseline (mechanism gate: candidate recall, gold-seeded 2-hop traversal, RBAC) before it ships.

## 2. Provenance and permission are non-negotiable

- No AI output mutates institutional memory until an authorized human approves it.
- Every surfaced graph fact carries a machine-checked verbatim source quote. Never show a summary without its evidence.
- Access control excludes confidential content **before** retrieval. Withheld sources are disclosed as a count only — never their content, title, or existence beyond that count.

## 3. Multi-tenancy is fail-closed

- Postgres: RLS `ENABLE` + `FORCE`; runtime connects as the non-superuser `callosum_app` role and sets `app.workspace_id`.
- Neo4j (no RLS): `workspace_id` is baked into entity MERGE identity and every read is scoped. All new/modified Neo4j access goes through the query gateway (`src/callosum/graph.py`); raw `session()` outside the gateway/allowlist is banned by test.

## 4. How we ship (incremental + measured)

- **Feature work is frozen (2026-08-01),** with one recorded exception below. The target is a portfolio-ready artifact by November. Only critical bug fixes, documentation, demo polish, deployment and evaluation reporting change. Deferred checkpoints (CP-F/G/H, #93) are **not** to be reopened because time remains — reopening them undoes the only thing that makes a deferral honest.
- **Exception, owner's decision 2026-08-04 — meeting preparation.** A `Prepare Meeting` flow is being built against the prototype at `devguru-codes.github.io/meridian_pre_intern_work`. It needs **no migration and no new domain module**: `packs` and `agenda` already expose create, reorder, publish and supersede from P2, and the flow is a frontend workflow over endpoints that already shipped. Recorded here rather than smuggled in as polish. **Two constraints hold inside it:** every suggestion is *derived from a real row and names it* — the agenda comes from open commitments and proposed decisions, never from a language model, because a generated agenda has no source and §2 forbids surfacing anything without one. And readiness reports **counts, not percentages**: the prototype's 90% / 55% / 40% have no denominators, and a percentage implies a measurement that was never taken. The prototype's Finance, HR, Product and CRM sources do not exist in this product and are not to be rendered.
- **One verified change per commit.** Smallest change that increases confidence. No drive-by refactors, no churn.
- Branch off the default branch; never commit straight to it. **Commit and push only when the owner asks.**
- Fix only real, reproduced bugs. Measure before refactoring — let the problem pick the work.
- Release cadence = merge → freeze → tag → graphify snapshot → publish notes → postmortem. A release is an immutable, self-contained bundle.

## 5. Ownership

- **Frontend** = maintainer/owner. **Backend** (domain model, migrations, RLS/tenancy, API contracts, tests, infra) = Devguru.
- Backend publishes stable contracts; the frontend consumes only those. **The API layer is real as of P3** — nine `lib/*` modules call it through `lib/http.ts`. The three that are still local (`graph`, `assistant`, `insights`) are recorded exceptions, not swaps waiting to happen; see [phase.md](./phase.md).
- **P3 interim (owner decision, 2026-07-29):** while Devguru is unavailable, the maintainer is
  backend owner so the phase does not stall. If he returns before CP-A implementation begins,
  review the design (ADR-009 – ADR-013) together and split the checkpoints then. **One owner
  during implementation** — two people building an auth layer from the same design is how
  architectural work gets done twice and agrees with itself nowhere. CP6/CP7 were taken the
  same way and handed back in #58.

## 6. Frontend design rules

Full system in [frontend/DESIGN.md](./frontend/DESIGN.md). The short version:

- **Semantic tokens only.** Components reference roles (`accent`, `surface-raised`, `muted-foreground`, `memory-emphasis`) — never a raw hex or a palette step (`blue-600`, `slate-100`).
- **Color communicates meaning (95% neutral / 5% semantic):** Blue = action · Green = success · Amber = pending/attention · Red = critical · **Violet = Institutional Memory only** (never a button or nav). No gradients, no neon, no glow-as-default.
- **Elevation, not color, reduces flatness.** Three levels: (1) normal white cards — subtle border + tiny shadow; (2) important cards (Meeting Hero, AI panel) — stronger elevation; (3) floating UI (dialogs, dropdowns, command palette) — blur. Blur/transparency is reserved for the header, AI sidebar, and floating UI; dashboard cards stay solid white for readability.
- **Light-mode only.** Cards 16px radius, controls 12px, badges fully rounded.
- **WCAG 2.2 AA is a hard floor.** Body text ≥4.5:1 (large ≥3:1), visible non-color-only focus rings, full keyboard paths, `prefers-reduced-motion` alternatives.
- Voice is plain and calm — no sci-fi theatrics.

## 7. Environment

- The owner runs long/heavy commands (dev server, builds, eval, migrations) themselves in Kitty (fish shell). Provide one-line, copy-pasteable commands; don't run them from an agent tool.
- Python via `uv` (`uv pip install`, not `pip`). Frontend: Next 16 + React 19 + Tailwind v4. `ollama` runs as a systemd service — never suggest `ollama serve`.
