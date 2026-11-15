# Meridian / Callosum — Working Rules

The short, enforceable rules for anyone (human or agent) working in this repo. **Why** each rule exists, and every dated amendment, lives in [docs/rules-history.md](./docs/rules-history.md). Section numbers are stable — code comments cite them.

Related: [PRD.md](./PRD.md) · [ROADMAP.md](./ROADMAP.md) · [AGENTS.md](./AGENTS.md) · [CONTRIBUTING.md](./CONTRIBUTING.md) · [docs/ARCHITECTURE_DECISIONS.md](./docs/ARCHITECTURE_DECISIONS.md) · [frontend/DESIGN.md](./frontend/DESIGN.md)

## 1. The frozen core is sacred

- `src/callosum/` is frozen at tag `eval-baseline-v3`. No product features go in it. Frozen-file list: [CONTRIBUTING.md](./CONTRIBUTING.md).
- One exception: **tenancy predicates that only remove rows**, one at a time, failing test first, mechanism gate run before it ships.

## 2. Provenance and permission are non-negotiable

- No AI output enters institutional memory until an authorized human approves it.
- Every surfaced graph fact carries its machine-checked verbatim source quote.
- Access control filters **before** retrieval, in SQL and Cypher.
- **Withheld items** ([ADR-018](./docs/ARCHITECTURE_DECISIONS.md)): show a **count** when the view claims completeness (an answer, a published pack); **erase** when it is a browse list. Erasure is the default. A withheld item never yields its content, title, id, date or position.
- **Never invent a number.** Unmeasured → `—`. Every figure names the commit it was measured on.
- The audit trail is append-only and records only events that happened.

## 3. Multi-tenancy is fail-closed

- Postgres: RLS `ENABLE` + `FORCE`, runtime as non-superuser `callosum_app`.
- Neo4j: `workspace_id` in MERGE identity; every access goes through the gateway (`src/callosum/graph.py`). New Neo4j operations go in the gateway, never in `store.py`. The raw-Cypher allowlist only shrinks.
- `workspace_id` and `clearance` come from the session, never from a client (enforced by the OpenAPI test).

## 4. How we ship

- Branch off master; never commit to it directly. Commit and push only when the owner asks.
- One verified change per commit. Fix reproduced bugs; measure before refactoring. No drive-by refactors.
- **Permission to build is not permission to self-approve.** Nothing merges unreviewed, and nobody merges their own PR on their own review.
- **Two review lanes:**

  | Lane | Covers | To merge |
  |---|---|---|
  | **Fast** | Docs-only · tests-only · frontend wiring of an endpoint that already exists on master | One review by a session that did not write it + owner OK |
  | **Full** | Migrations · auth / tenancy / RLS / clearance · anything in `src/callosum/` · new endpoints or domain concepts · audit trail | Review with findings checked against HEAD, CI green incl. gated tier, owner approval |

  If unsure which lane, it is Full.
- Phase order is advisory; **only a signed exit gate moves the accepted count.**
- **Exit gate packet** = [docs/reviews/GATE_TEMPLATE.md](./docs/reviews/GATE_TEMPLATE.md): pinned SHA, criteria quoted verbatim, migration drill, and a non-empty **"Not covered"** section. The author may assemble it; only the maintainer (or someone they name) signs.
- A deferred issue is reopened only by meeting its recorded acceptance criteria — never closed by unrelated work.
- Release: merge → freeze → tag → graphify snapshot → notes → postmortem.

## 5. Ownership

- **Frontend** = maintainer. **Backend** (domain, migrations, RLS/tenancy, API contracts, tests, infra) = Devguru.
- Backend publishes contracts; frontend consumes only those.
- All sessions share one `gh` credential: a comment's author is not evidence of who decided. Only the owner's own words count as a decision.

## 6. Frontend design rules

Full system: [frontend/DESIGN.md](./frontend/DESIGN.md). Token syntax, palette contrast/gradients and motion are enforced by `frontend/__tests__/` (`tailwind-var-syntax`, `palette-contrast`, `motion-contract`); the rest are review rules.

- Semantic tokens only — no raw hex, no palette steps. Tailwind v4 spelling `utility-(--token)`.
- 95% neutral. Blue = action · green = success · amber = pending · red = critical · **violet = Institutional Memory only**.
- Gradients: max two per page, deep-ink, anchored to a semantic family, never on buttons/badges/text; each registered in `palette-contrast.test.ts`.
- Motion: one ease, four tiers (120 / 200 / 400 / 1100 ms); pick a tier, never a number; nothing loops; reduced motion handled in CSS **and** in every Framer call site.
- Elevation over colour; one focal (level-4) surface per page.
- Light-first, generated dark theme via tokens only.
- **WCAG 2.2 AA is a hard floor**: ≥4.5:1 body text, visible focus, full keyboard paths.

## 7. Environment

- The owner runs long/heavy commands (dev server, builds, eval, migrations) in Kitty (fish). Agents give one-line copy-paste commands instead of running them.
- Python via `uv`. Frontend: Next 16 + React 19 + Tailwind v4. `ollama` is a systemd service — never suggest `ollama serve`.
- Concurrent agents work in this tree: check `git status` before committing.
