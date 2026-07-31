# Session review — frontend registries, dashboard charts, roadmap sync

**Date:** 2026-07-25 → 2026-07-26
**Repo:** `github.com/Cloverag/callosum` (private)
**Reviewer's job:** challenge the decisions below. Sections marked **⚠ CHALLENGE THIS**
are where I am least confident.

---

## 1. What this session touched

| Artefact | State |
|---|---|
| Branch `feat/frontend-registries` | 6 commits, pushed, **no PR opened** |
| PR #24 — `docs/roadmap-progress-sync` | Open |
| PR #25 — `feat/frontendglass-board-os` | Open, build now confirmed green |
| PR #22 — Devguru's CP4 Decision | Not mine; posted a follow-up nudge |
| `graphify-out/` knowledge graph | Rebuilt + 60 communities labelled |

Branch stack (verified with `git merge-base --is-ancestor`, strictly linear):

```
master ──> feat/frontend-design-system ──> feat/frontend-redesign-v2
       ──> feat/frontendglass-board-os  (= PR #25)
       ──> feat/frontend-registries     (this session's new work)
```

`feat/frontend-registries` is stacked **on top of PR #25**, which is itself unmerged.
Nothing here reaches `master` until #25 does.

---

## 2. Commits on `feat/frontend-registries`

| SHA | Subject |
|---|---|
| `54e0e1d` | wire KokonutUI / Animate UI / Bklit UI registries onto the token layer |
| `573545f` | add the missing `test` npm script |
| `a47bb34` | correct registry URLs, item naming, and retoken coverage |
| `254211a` | vendor Animate UI tooltip + Bklit charts, reconciled to the tokens |
| `13116a1` | memory growth chart + glossary tooltips on graph health |
| `c619f9f` | rebuild memory growth chart on the emphasis form |

---

## 3. The core problem this branch solves

KokonutUI, Animate UI and Bklit UI are **shadcn registries**. This repo's frontend
is *not* shadcn — it has hand-authored primitives (`src/components/ui/`) on a
semantic token layer (`globals.css`). Registry source is written against shadcn's
token vocabulary, so it does not inherit this design system for free.

### Approach taken

1. **`components.json`** — hand-written, with all three registries. The `ui` alias
   points at `src/components/vendor` so `shadcn add button` can never overwrite
   `src/components/ui/button.tsx`.
2. **`src/app/shadcn-compat.css`** — maps shadcn's vocabulary onto the semantic
   tokens (`background`→`surface`, `card`→`surface-raised`, `primary`→`accent`,
   `muted`→`surface-sunken`, `ring`→`focus`, sidebar block, chart vars). Aliases
   only — no hex, no palette steps, so the repo's Semantic-Only rule survives.
3. **`scripts/retoken.mjs`** — a codemod for what a declarative bridge cannot do.

> **Do not run `npx shadcn init`.** It rewrites `globals.css` with shadcn's default
> token block. `components.json` was hand-written precisely so `add` works without it.

---

## 4. Findings, with evidence

### 4.1 `accent` means the opposite thing in each system

shadcn: `accent` = subtle hover surface (`focus:bg-accent`).
Meridian: `accent` = solid ACTION blue. **18 shipped call sites** depend on that.

Cannot be bridged — one name, two meanings. `retoken` rewrites the shadcn sense out
of vendored files (`bg-accent`→`bg-surface-sunken`,
`text-accent-foreground`→`text-foreground`). Verified it preserves
`bg-accent-subtle`, `bg-accent-hover`, `border-accent-border`, `rounded-md`.

### 4.2 `shadcn add` appended a broken chart block to `globals.css`

This is the one that produced a visibly grey chart. The CLI appended, at the bottom
of the file:

- an **unlayered `:root`** with `--chart-1: oklch(0.32 0 none)` (grayscale).
  Unlayered CSS beats `@layer base`, so it overrode the violet mapping.
- a `.dark` block, in an app that is **light-only** (the v2 pivot removed
  next-themes entirely).
- an `@theme inline` containing **26 refs of the form `var(----chart-1)`** — four
  dashes. Every `--color-chart-*` utility was silently dead.

Removed. Verified in the production bundle, not asserted:

```
--chart-1:var(--memory)      --memory:#6d28d9
occurrences of oklch(0.32 0 none): 0
```

### 4.3 Bklit reads ~24 `--chart-*` custom properties directly

`var(--chart-grid)`, `--chart-crosshair`, `--chart-tooltip-background`,
`--chart-line-primary`, `--chart-scale-01..05`… `@theme` aliases never reach these.
All mapped onto the neutral + memory scales. A script confirms every CSS var
referenced by any component now resolves.

### 4.4 The vendored tooltip would have rendered as a solid blue bubble

It used `bg-primary`. In stock shadcn `primary` is near-black, so it doubles as
button fill *and* dark chrome. Here `primary` maps to ACTION blue.
Rewrote the vendored component to a neutral dark bubble.

**Deliberately not automated** — `bg-primary` is *correct* on a button and *wrong*
on a tooltip, so a codemod would have to guess.

### 4.5 Registry layout vs. CLI layout

Bklit ships `src/charts/*` and `src/components/*` as siblings, so
`../components/shimmering-text` is right in their repo. The CLI re-homed charts
*into* `src/components/charts/`, so the specifier overshot into a
`src/components/components/` that does not exist. **This broke the build.**

`retoken` gained an import-repair phase: it only touches imports that already fail
to resolve, and only rewrites when exactly one candidate matches the basename.
Ambiguous cases are reported, never guessed. Verified: 65 files, 0 broken imports
after the pass.

### 4.6 Things I got wrong mid-session (worth knowing)

- I guessed `@animate-ui/tooltip`. Wrong — Animate UI names are **hyphenated with a
  flavour prefix** (`components-radix-tooltip`), 580 items. I only found this by
  fetching `https://animate-ui.com/r/registry.json`. **I should have checked the
  registry index before handing over a command.**
- `ui.bklit.com/r/*` 301-redirects to `bklit.com/r/*`. Now pinned.
- `@kokonutui/utils` is `registry:lib` targeting `/lib/utils.ts` and would overwrite
  the repo's `cn`. Dropped from the install. `src/lib/utils.ts` **was** overwritten
  anyway by something in the dependency chain — damage was cosmetic (import order
  only) and I reverted it, but **a reviewer should watch this on future installs.**

---

## 5. The chart — where I was wrong and the validator corrected me

I wrote chart code **before** loading the `dataviz` skill. I should have loaded it
first; its own trigger says to read it before the first line of chart code.

First version: two series (edges, entities) as two filled areas in two steps of one
violet (`--memory` #6d28d9 and `--memory-soft` #8b5cf6). Ran the validator instead
of trusting my eye:

```
violet-700 vs violet-500 → normal-vision ΔE 11.7   FAIL  (floor is 15)
violet-700 vs slate-500  → normal-vision ΔE 21.9   PASS
```

Below the normal-vision floor = hard to tell apart **even with full colour vision**,
and that check cannot be waived by adding labels. It also matched a listed
anti-pattern: *categorical hues when the story is emphasis*.

### Rebuilt on the emphasis form

- **Edges** — the point — filled area in memory violet.
- **Entities** — context — bare 2px line in `subtle-foreground` grey, no fill
  (also removes the occlusion of two translucent stacked fills).
- Identity rests on **three** cues: name, value, mark shape (filled swatch vs rule).
- Legend carries each series' current value, doubling as the direct label.
- Text in ink tokens; only swatches coloured.
- The grey trips a contrast WARN (<3:1), which obliges a non-visual route to the
  numbers — the tooltip is hover-only, so a **"View as table"** disclosure ships.

This also resolves the doctrine tension: violet stays Institutional Memory, blue
stays ACTION, and no third hue was invented to seat a second series.
`DESIGN.md` now records the measurement and the rules that follow.

---

## 6. Verification status — read this before trusting anything above

**Verified by running it:**
- `npm run build` — green, 10/10 routes prerendered.
- `npx tsc --noEmit` — **0 errors in `src/`**.
- Production CSS bundle contains `--chart-1:var(--memory)` → `#6d28d9`; zero
  grayscale oklch.
- Every CSS var referenced by any component resolves (script).
- 65 vendored files, 0 unresolved relative imports (script).
- `retoken` behaviour: rewrites correctly, preserves the `-subtle`/`-hover` variants,
  `--check` exits 1, `retoken src/components/ui` refuses with exit 2.
- Palette ΔE numbers — from `dataviz/scripts/validate_palette.js`, not judgement.

**NOT verified:**
- ⚠ **Nobody has looked at the rendered chart.** Build passing ≠ it looks right.
  Layout, label collisions, and whether the card reads too heavy in the band are
  all unchecked. The dataviz skill explicitly requires a visual pass; it has not
  happened.
- `npm test` — the script now exists (`573545f`) but the suite was not run this
  session. There is a known-failing jsdom test tracked as issue #15.
- Pre-existing `@types/jest` errors in `__tests__/` (unrelated to this branch).
- No accessibility audit beyond palette contrast and keyboard-reachable tooltips.

---

## 7. ⚠ CHALLENGE THIS — open questions for the reviewer

1. **Is Bklit worth its footprint?** ~60 vendored files, `@visx/*` pinned at
   `4.0.1-alpha.0` (alpha deps in a final-year project that will be defended), and
   a second copy of Motion alongside `framer-motion@12` — to draw one area and one
   line. The repo already has good hand-rolled SVG primitives (`Gauge`, `Sparkline`,
   `StatBar`). **My honest view: this one chart is ~80 lines of SVG and Bklit may
   not earn its place. I did not push back hard enough before installing.**
2. **`motion` + `framer-motion` coexisting.** Same library, both names, until
   imports migrate. Nobody has decided when.
3. **Two frontends in the repo.** `frontend/` (Next.js) and
   `frontendglass/meridian-glass/` (Vite). Recorded in `phase.md` as undecided.
   Must be settled before P3 wires a real API.
4. **The seeded `memoryGrowth` data is invented** except its final point, which is
   the real p1.0.4 snapshot (731 entities / 1277 edges). The intermediate weeks are
   plausible fiction. Fine for a mock; **must not survive into a real API.**
5. **Chart colour for non-memory series is still unsolved.** Violet is reserved for
   memory, blue for action — so there is no categorical palette. Currently deferred
   with a note in `DESIGN.md`. A meeting-mix-by-status chart will hit this.
6. **`--chart-scale-01..05` (heatmap ramp) is defined but unused** — no heatmap is
   installed. Speculative; arguably should be deleted until needed.

---

## 8. Non-frontend work in this session

- **PR #24** — `ROADMAP.md` progress table said *"0 / 13 accepted · P0 authorized"*,
  dated 2026-07-17, while P0 and P1 had shipped and P2 was four checkpoints in.
  Corrected to 2/13, added a P2 checkpoint table, and **recorded the CP3 skip in the
  roadmap itself** (the operating rule requires an exception to carry an owner and
  due checkpoint; it existed only in issue #23).
- **PR #22 nudge** — Devguru had not responded to the CP4 review in ~24h. Restated
  the two blocking changes (missing decision-status guard on `record_stance()`;
  `ON CONFLICT … SET created_at = now()` destroying audit history). No code written
  by me — backend is Devguru's ownership.
- **Knowledge graph** — `graphify update` (AST-only, zero LLM cost) → 2062 nodes,
  3011 edges, 219 communities at commit `e40e064`. Labelled 60 communities covering
  1340/2062 nodes. Highest-betweenness node is `retrieve.py` (0.026), bridging nine
  communities including the eval harness — a structural argument for the
  frozen-core rule.

---

## 9. Suggested review order

1. `frontend/src/app/shadcn-compat.css` — is the token mapping semantically honest?
2. `frontend/scripts/retoken.mjs` — is the import-repair heuristic too clever?
   It rewrites source based on filename matching.
3. `frontend/src/app/dashboard/memory-growth.tsx` — **render it and look at it.**
4. `frontend/DESIGN.md` (Registry components + chart rules) — do the recorded rules
   actually follow from the measurements?
5. Question 7.1 above — the Bklit footprint decision.
