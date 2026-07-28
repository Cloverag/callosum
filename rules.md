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

- **One verified change per commit.** Smallest change that increases confidence. No drive-by refactors, no churn.
- Branch off the default branch; never commit straight to it. **Commit and push only when the owner asks.**
- Fix only real, reproduced bugs. Measure before refactoring — let the problem pick the work.
- Release cadence = merge → freeze → tag → graphify snapshot → publish notes → postmortem. A release is an immutable, self-contained bundle.

## 5. Ownership

- **Frontend** = maintainer/owner. **Backend** (domain model, migrations, RLS/tenancy, API contracts, tests, infra) = Devguru.
- Backend publishes stable contracts; the frontend consumes only those (or mocks until the P3 API exists). No API layer exists yet — all frontend data is mock-driven.
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
