---
name: Meridian Board OS
description: Calm, provenance-first board operating system — neutral light surface, one blue action color, violet reserved for institutional memory.
colors:
  accent: "#2c70e5"
  accent-foreground: "#ffffff"
  accent-hover: "#1b57bb"
  accent-emphasis: "#245bb9"
  accent-subtle: "#eef4ff"
  accent-border: "#c7dcff"
  success: "#00873c"
  success-emphasis: "#016e30"
  warning: "#f5a32f"
  warning-emphasis: "#865400"
  danger: "#d53d3a"
  danger-emphasis: "#ad3230"
  info: "#2c70e5"
  memory: "#855bdc"
  memory-emphasis: "#6c4ab3"
  memory-soft: "#8f6ce0"
  foreground: "#0f1926"
  muted-foreground: "#475567"
  subtle-foreground: "#647489"
  border: "#e3e7ec"
  border-strong: "#cdd3dc"
  focus: "#2c70e5"
  surface: "#f6f8fa"
  surface-elevated: "#ffffff"
  surface-raised: "#ffffff"
  surface-alt: "#f1f3f6"
  surface-sunken: "#ebeff3"
typography:
  display:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.875rem"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.375rem"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.01em"
  section:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
  metadata:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "normal"
  label:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "normal"
  caption:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 500
    lineHeight: 1.35
    letterSpacing: "normal"
  micro:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.625rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "0.08em"
rounded:
  sm: "6px"
  control: "12px"
  card: "16px"
  modal: "20px"
  full: "9999px"
spacing:
  xs: "8px"
  sm: "12px"
  md: "16px"
  lg: "24px"
  xl: "32px"
  "2xl": "40px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-foreground}"
    rounded: "{rounded.control}"
    padding: "10px 20px"
    typography: "{typography.body}"
  button-secondary:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.control}"
    padding: "10px 20px"
    typography: "{typography.body}"
  input:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.control}"
    padding: "0 14px"
    typography: "{typography.body}"
  badge:
    backgroundColor: "{colors.surface-sunken}"
    textColor: "{colors.muted-foreground}"
    rounded: "{rounded.full}"
    padding: "2px 10px"
    typography: "{typography.caption}"
  card:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.card}"
    padding: "20px"
  nav-item:
    backgroundColor: "{colors.accent-subtle}"
    textColor: "{colors.accent-emphasis}"
    rounded: "10px"
    padding: "8px 10px"
    typography: "{typography.body}"
---

# Design System: Meridian Board OS

## 1. Overview

**Creative North Star: "The Calm Desk."**

Meridian is the software a founder, chief of staff, or director opens the hour before a board meeting and instantly trusts. The interface is a calm, well-lit desk: a soft neutral page, white cards that sit like physical sheets, hairline structure, and exactly one trustworthy blue that appears only where it means *do this*. Dense governance information — decisions, evidence, provenance, readiness, access — sits legibly side by side without shouting. The system's job is to disappear into the task and make the *record* the hero.

This is a **light-first** product: the light palette is the tuned one, and the one every screenshot and review is judged against. **A dark theme was added 2026-08-09** (owner's decision, recorded in `rules.md` §4) — generated the same way, not inverted from it, and held to the same AA floor. The palette explicitly rejects what this product is not: the dated weight of enterprise board portals (Diligent, Boardvantage), the gradient hero-metric tiles and identical card grids of generic SaaS dashboards, crypto/fintech neon, and decoration-over-density productivity apps with oversized cards and wasted whitespace. Trust here is legibility under scrutiny, not atmosphere.

**Key characteristics**
- **95% neutral, 5% semantic color.** Every color carries one meaning; color is never decoration.
- **One action color — blue `#2563EB`** — for primary buttons, active navigation, links, focus rings, selected states, and calendar events. Nothing else is blue.
- **Violet `#6D28D9` is the Institutional-Memory identity**, reserved exclusively for memory surfaces (graph health, provenance, memory metrics, trend charts). Never a button, never navigation.
- **White cards on a soft neutral page**, separated by 1px hairlines and a very subtle shadow — sheets on a desk, not floating glass.
- **Inter throughout**, hierarchy from weight and size, not font contrast.
- **WCAG 2.2 AA is a hard floor** — every text/surface pairing passes 4.5:1 (large text 3:1).

**Density doctrine.** Meridian is dense but calm — never "minimal." Optimize for seeing more meaningful information without overwhelming the operator; reduce decorative elements before reducing content.

**Motion hierarchy** (see `globals.css` tokens `--duration-hover` 120ms, `--duration-state` 200ms):
- **L0 — None:** static content being scanned.
- **L1 — Hover / press (120ms):** state feedback on interactive elements.
- **L2 — State transitions (200ms):** dialog/popover open-close, list reflow, progress fills.
- **Reduced motion:** all non-essential motion collapses to instant/crossfade (enforced globally).

## 2. Colors

A restrained light palette expressed as **semantic tokens, not palette steps** — components reference roles (`accent`, `surface-raised`, `muted-foreground`, `memory-emphasis`), never a raw hex or a `blue-600`.

**Rebuilt 2026-08-09 in OKLCH (owner's decision, recorded in `rules.md` §4).** Three
things were measured wrong in the palette this replaces: the neutrals were drawn
from two Tailwind families (`gray` + `slate`) and spread **16.8° of hue**;
`surface-alt` sat **ΔL\* 0.52** from `surface`, below the ~1.0 just-noticeable
difference, so one rung of the tonal ladder was invisible; and `danger-emphasis`
**failed AA at 4.41:1** on `surface-sunken` while this section claimed every
pairing was verified.

The replacement holds **one neutral hue anchor (H=255)**, puts surfaces on
visible L\* steps (100 / 97.8 / 96.4 / 95.0), and **solves** each semantic ink
for ≥5.5:1 against the darkest surface it can sit on instead of choosing it by
eye. Solving every ink to one target is why they read as one family: each
`-emphasis` lands in a **5.5–6.4** band, so no status colour shouts louder than
another for a reason nobody chose. **Worst pairing in the system is 5.54:1**
against a 4.5 floor — the figures below are generated, and reproducible from the
token values.

### Action — Blue (`#2C70E5`)
The one interactive color. `accent` fills the primary button and selected state (white label **4.61:1**); `accent-hover` (`#1B57BB`) is the hovered fill; `accent-emphasis` (`#245BB9`) writes accent-as-text and icons (**6.42:1** on white, **5.55:1** on the darkest surface); `accent-subtle` (`#EEF4FF`) is the active-nav / selected-row wash; `accent-border` (`#C7DCFF`) its hairline. **Used only for action** — buttons, active navigation, links, focus rings, selected tabs, checkboxes, calendar events. Never for success/warning, never decoration.

### Status
Each ships a solid (fills/dots), a `-foreground` (label on the solid), an `-emphasis` (AA text/icon on a surface), and a `-subtle` (wash). **The `-subtle` washes are solid colors, not alpha** — as `rgba()` they took their value from whatever sat behind them, so the same badge was not the same colour on a white card and in a sunken well.
- **Success — Green `#00873C`** (emphasis `#016E30`): verified, completed, approved, healthy.
- **Warning — Amber `#F5A32F`** (foreground `#422700` on the amber fill, **6.68:1**; emphasis `#865400`): pending review, draft, awaiting approval. Amber is the one fill carrying a *dark* label, because an amber dark enough to hold white text has stopped being amber.
- **Danger — Red `#D53D3A`** (emphasis `#AD3230`): errors, overdue, failed, quarantined, destructive actions.
- **Info** maps to the action blue — informational status shares the one blue.

### Institutional Memory — Violet (`#855BDC`)
The product's identity color, **reserved for institutional-memory surfaces only**: graph health, the verified-share gauge, provenance, memory metrics, and memory trend charts. `memory-emphasis` (`#6C4AB3`, **6.43:1** on white) writes text/icons and draws the gauge/sparkline; `memory-soft` (`#8F6CE0`, **3.90:1** — above the 3.0 graphic floor, never body text) is for large/secondary graph elements; `memory-subtle` a faint wash. **Never a button, never navigation** — that is what makes it read as *memory* and gives Meridian a unique identity.

### Neutral
Tonal elevation, base upward, on **one hue anchor** and steps that clear the just-noticeable difference: **Surface** (page base `#F6F8FA`, L\* 97.8), **Surface-elevated** (sidebar, header, AI rail, panels — `#FFFFFF`), **Surface-raised** (cards, dialogs, popovers — `#FFFFFF`, L\* 100), **Surface-alt** (secondary/nested panel `#F1F3F6`, L\* 96.4), **Surface-sunken** (inset wells, quote blocks — `#EBEFF3`, L\* 95.0).
- **Text / `foreground`** `#0F1926`: primary text and headings. **17.69:1** on white.
- **Text-muted / `muted-foreground`** `#475567`: secondary text, labels, timestamps. **7.60:1** — AA on every surface.
- **Subtle / `subtle-foreground`** `#647489`: large or decorative text only — never body.
- **Border** `#E3E7EC`, **Border-strong** `#CDD3DC`: hairline separators. Never a heavy or colored stripe.
- **Focus** `#2C70E5`: the focus-ring color; a 2px ring, ≥3:1 against its surface.

### Dark theme

Delivered **entirely by re-pointing the semantic tokens** — not one component changed, because none of them names a colour. That is the payoff of the Semantic-Only rule, and the audit that proved it: zero `bg-white`, zero `text-white`, zero raw hex across every `.tsx` in the app.

Three things are deliberately *not* mirror images of the light theme:

- **Elevation runs the other way.** On a dark ground a raised surface is *lighter* and an inset well is *darker*, so the ladder reverses: sunken L\* 17 → surface 20.5 → raised 24.5 → alt 28.5.
- **Chroma comes down.** Saturated colour on a dark ground muddies rather than enriches, so the neutrals carry less chroma and the inks get *lighter* rather than more saturated.
- **Fills carry a dark label.** An accent light enough to read on this ground cannot also hold white text — `accent-foreground` inverts.

Each coloured ink is solved for ≥5.5:1 against `surface-alt`, the **lightest of the four base surfaces** and so the worst case among them — the mirror of the light theme, where the darkest surface was. **Zero AA failures across 7 inks × 9 surfaces; worst pairing 5.14:1.**

**The ≥5.5:1 solve covers the four base surfaces, not all nine** (corrected 2026-08-13). On the five `-subtle` washes the coloured inks land between **5.14:1 and 5.49:1** — above the 4.5:1 AA floor everywhere, below the 5.5 target the neutrals hold. The two sentences above previously stated a ≥5.5 solve and a 5.14 worst pairing one clause apart, which cannot both be true of the same set; the figure was true of the base surfaces and had been generalised. Nothing was inaccessible and nothing moved in the palette — the prose was wrong, not the tokens. Both claims are now asserted separately by `frontend/__tests__/palette-contrast.test.ts`, so the distinction cannot collapse again. Light is unaffected: it clears 5.5:1 on all nine.

### Focal surfaces — elevation level 4 *(added 2026-08-13)*

Two ramps, and no others. They are palette members, not one-off styling, which is why their values live here rather than in a component.

| Token | Ramp | Worst stop vs `--focal-foreground` (`#FFFFFF`) |
|---|---|---|
| `--focal-action` | `#101A28` → `#1D4285` | **9.68:1** |
| `--focal-memory` | `#101A28` → `#4A2E8C` | **10.19:1** |

Both share the ink end, so the two focal surfaces on a page read as one material at different temperatures rather than two competing brand colours. `action` carries the operational hero because that surface holds the primary button; `memory` carries the institutional-memory band. **The semantic families are unchanged** — this buys depth, not a new vocabulary, and violet still never means "button".

The dark theme narrows both ramps rather than brightening them: a focal surface on a dark ground should read as a *material*, not a light source. Every stop of every ramp is asserted against `--focal-foreground` in `frontend/__tests__/palette-contrast.test.ts`, which checks **all stops** rather than a declared worst one, so a future edit to either end cannot slip past by moving which stop is darkest.

The theme marker is **`data-theme` on `<html>`**, never a `.dark` class. Tailwind's `dark:` variant stays bound to a `.dark` we never apply, so vendored registry components cannot apply a *second*, uncoordinated adjustment on top of the token flip. `color-scheme` is set per theme at the root, so native date pickers, spinners and scrollbars follow without per-control classes. The default is **system**; a choice is stored under `meridian.theme` and applied by an inline pre-paint script, because a deferred one runs after the document has already painted the wrong theme.

### Named rules
- **The Semantic-Only Rule.** Components consume semantic tokens exclusively. A raw hex, a `blue-600`, or a `slate-100` inside a component is a bug — it breaks theming and AA at once.
- **The One-Action Rule.** Blue means *action*. It appears on primary action, active nav, links, focus, selection — and nowhere else. Blue to "brighten up" a panel is a bug.
- **The Memory-Only Violet Rule.** Violet appears only on institutional-memory surfaces. Violet anywhere else — a button, a nav item, a generic accent — is a bug.
- **The Neutral-Page Rule.** Page base is neutral `#F7F8FA` and cards are white; separation comes from hairlines and a subtle shadow, never a tint.

## 3. Typography

**Font:** Inter (`ui-sans-serif, system-ui, sans-serif` fallback). One family, tuned across weight and size — no display/body pairing.

### Ramp (fixed rem scale, not fluid)
- **Display** (700, 1.875rem / 30px, tracking -0.02em): page titles ("Dashboard") — the largest type on any working surface.
- **Title** (600, 1.375rem / 22px): object names, hero meeting title, panel titles.
- **Section** (600, 1.125rem / 18px): card/section headings.
- **Body** (400, 0.875rem / 14px, line-height 1.6): the default — descriptions, quotes, table cells. Prose capped 65–75ch.
- **Metadata** (500, 0.8125rem / 13px): dense secondary data — shortcut chips, list values, meeting meta.
- **Label** (600, 0.75rem / 12px): control labels, badges, counts.
- **Caption** (500, 0.6875rem / 11px): the smallest metadata tier — timestamps, source captions, rail status. The density tier.
- **Micro** (600, 0.625rem / 10px, tracking 0.08em, uppercase): section eyebrows and provenance micro-labels only.

### Named rules
- **The Fixed-Scale Rule.** Type is a fixed rem scale, never fluid `clamp()`. A heading that shrinks in a sidebar is a regression.
- **The Quiet-Label Rule.** Uppercase tracked micro-labels are for true metadata and one section eyebrow — never stacked above every block.

## 4. Elevation

**Flat by default, layered by role.** Depth is tonal first (neutral page → white card), shadow second, and shadows are *very* subtle. Reduce flatness with **spacing and elevation, not more color**. Three deliberate levels:

- **Level 1 — Normal cards** (`shadow-card`, white + 1px hairline + tiny shadow): the default. Board Readiness, Needs You, Recent Decisions, Approved Facts, Graph Health.
- **Level 2 — Important cards** (`shadow-raised` + a `border-strong` hairline): the Meeting Hero and the AI panel — the surfaces the eye should land on first. Slightly stronger elevation, never a color change.
- **Level 3 — Floating UI only** (`.surface-glass` = blur + translucency + `shadow-overlay`): dialogs, popovers, dropdowns, command palette. The only surfaces that leave the page plane.

**The Blur-Is-Chrome-or-Floating Rule.** Backdrop-blur / translucency appears in exactly three places: the **header**, the **AI rail** (both use `.surface-glass-chrome` — the glass tint with a gentler blur and no floating shadow, because they are anchored chrome), and **Level 3 floating UI**. **Dashboard content cards stay solid white** for readability — glass on a content card is a bug. The left navigation sidebar is solid, not glass.

## 5. Components

Hairline borders, `control` (12px) / `card` (16px) radii, pill badges, quiet defaults that respond crisply to state. Every interactive component ships default, hover, focus-visible, active, disabled, and (where it loads) loading.

- **Buttons** — 12px radius. **Primary:** solid blue fill (`accent`), white label, `accent-hover` on hover — the one dominant action per surface. **Secondary:** white with a gray border. **Ghost:** transparent, muted label, sunken wash on hover. Focus-visible shows a 2px blue ring at ≥3:1.
- **Badges** — full-radius pills; card/status wash + emphasis label. Neutral by default; a colored tone only for real status.
- **Cards** — 16px radius, white surface, 1px hairline, `shadow-card`. 20–24px padding on primary cards; tighter on dense rows. Never a colored side-stripe. **Nested cards are prohibited.**
- **Inputs** — 12px radius, white fill, hairline border; focus shifts the border to blue plus a soft blue ring.
- **Sidebar** — 248px, white surface. Nav items are body-size, muted at rest; **active shows a soft-blue wash (`accent-subtle`) with blue label and icon** — no side-stripe.
- **AI rail** — persistent 368px right column (collapsible to a 56px strip via ⌘/Ctrl+J), white surface. Proactive greeting, quick shortcuts, recent decisions, supporting documents, and evidence-cited answers. Every answer shows a source quote and a Verified marker; withheld sources appear as a count only.

### Signature surfaces
- **Institutional Memory (violet zone).** The graph-health gauge and review-throughput sparkline render in `memory-emphasis` violet — the only place violet appears. Quality rows keep status dots (green/amber/red).
- **Approved-facts card.** Each fact shows its plain statement, the verbatim source quote in a sunken well, a **blue source link**, and a **green Verified** marker — evidence, not summaries.

### Primitives — Base UI

**Amended 2026-08-09 (owner's decision, recorded in `rules.md` §4).** The primitive
library is [Base UI](https://base-ui.com); `components.json` carries it as the
`base-` prefix on `style` (`base-nova`), which is where shadcn encodes the base —
there is no separate `base` key. Radix is gone: it was a whole umbrella package
serving one tooltip.

`ui/button.tsx`, `ui/input.tsx` and `ui/dialog.tsx` are built on Base UI
primitives. The **variant vocabulary stays Meridian's** — `primary | secondary |
ghost | danger`, not shadcn's `default | outline | destructive` — because this is
the design system and 45 call sites already speak it.

The dialog is the reason this was worth doing. It was built on the native
`<dialog>` element, which handled focus correctly but hardcoded
`id="dialog-title"`; the calendar mounts two dialogs, so the id was not unique
and the accessible name could resolve to the wrong heading. Base UI generates
those ids, so the defect is now structurally impossible rather than fixed by
hand.

**`Card` and `Badge` are deliberately NOT on a primitive.** Base UI has none for
them, and shadcn's are plain `div`/`span`. Rewriting 79 + 27 call sites to reach
the same DOM is churn, not a migration.

### Registry components

Third-party shadcn registries are available — **KokonutUI** (`@kokonutui`) and
**Bklit UI** (`@bklit`) for charts — alongside the default `@shadcn` registry.
*(Animate UI (`@animate-ui`) supplied the tooltip until 2026-08-09; that tooltip
was the last Radix consumer and now comes from `@shadcn` on Base UI.)* They are
configured in `components.json` and install into `src/components/vendor/`, never
into `ui/`: `ui/` is the design system and the CLI must not be able to overwrite
it. **That rule survives the Base UI move** — `ui/` consumes primitives from
`node_modules`, not generated files, so `retoken.mjs`'s refusal to rewrite
`src/components/ui` still holds.

Registry source is written in shadcn's token vocabulary, not ours. `src/app/shadcn-compat.css` maps that vocabulary onto our semantic tokens (`background`→`surface`, `card`→`surface-raised`, `primary`→`accent`, `muted`→`surface-sunken`, `ring`→`focus`, …), so a vendored component inherits Meridian colour without edits. This does not weaken the Semantic-Only rule — the bridge contains no hex and no palette steps, only aliases to tokens `globals.css` already owns.

**One token cannot be bridged: `accent`.** shadcn means a subtle hover surface; we mean ACTION blue, and shipped components depend on our meaning. `npm run retoken` rewrites the shadcn sense (`bg-accent`→`bg-surface-sunken`, `text-accent-foreground`→`text-foreground`) plus the radius utilities (`rounded-lg`→12px, `rounded-xl`→16px) in vendored files only. **Run it after every `shadcn add`** — skipping it renders vendored hover states as solid blue bars.

**Charts.** `chart-1…5` is a *sequential violet ramp* scoped to memory surfaces, because violet is reserved for Institutional Memory and blue for action — a generic categorical rainbow is not available to us. For non-memory charts (e.g. meeting mix by status) use the status tokens directly; they already carry the right meaning. A categorical palette for genuinely unordered non-memory series is an **open decision**, not something to improvise per chart.

**Multi-series memory charts use emphasis, never two steps of one violet.** One series carries `memory` violet as the emphasised mark; the rest recede to `subtle-foreground` grey. This is measured, not preferred: violet-700 against violet-500 scores **ΔE 11.7** for normal vision — below the 15 floor, i.e. hard to tell apart *even with full colour vision* — while violet against slate-500 scores **21.9**. Pair it with a mark-shape difference too (filled area for the emphasised series, bare line for context) so identity never rests on hue alone.

Rules that follow from that, and apply to every chart here:
- **Never a dual axis.** Two measures at different scales become two charts or one indexed to a common base.
- **A legend is always present at two or more series**, and carries each series' current value so it doubles as the direct label. Never a number on every data point.
- **Text wears ink tokens, never the series colour** — only the swatch is coloured.
- **A grey series below 3:1 contrast obliges a non-visual route to the numbers.** The hover tooltip is not enough on its own; ship the table view alongside it.
- Gridlines and axes are solid hairlines one step off the surface — never dashed.

## 6. Do's and Don'ts

### Do
- **Do** keep blue to *action only* (≤5–10% of any screen) and violet to *memory only*.
- **Do** convey depth by tonal layering (neutral page → white card) first, subtle shadow second.
- **Do** derive nav/tab active state from the current route (`usePathname`).
- **Do** give every interactive element a visible, non-color-only focus ring and a full keyboard path; make citation/source interactions keyboard-operable.
- **Do** provide a `prefers-reduced-motion` alternative for every transition; keep state transitions 150–250ms.
- **Do** signal status with a shape/label/icon in addition to color.
- **Do** keep information density high: tight, legible rows and short paths to common actions.

### Don't
- **Don't** style like an enterprise board portal (Diligent, Boardvantage) or a generic SaaS dashboard (gradient hero-metric tiles, identical icon-heading-text card grids).
- **Don't** use violet for buttons or navigation, or blue for success/warning — each color has one meaning.
- **Don't** use neon, glow-as-default, or glass on content cards.
- **Do** use gradients only on a **registered focal surface** *(amended 2026-08-13, owner's decision — this rule previously read "don't use gradients"; see `rules.md` §6)*. Three things hold, and a gradient failing any of them is still a defect:
  1. **Anchored to a semantic family.** The operational hero ramps ink→blue-ink because it carries the primary action; the institutional-memory panel ramps ink→violet-ink. Violet still never means "button" — the amendment buys depth, not a new vocabulary.
  2. **At most two per page**, deep-ink based, linear, low chroma. Never on a button, badge, chip, chart, icon, small panel, or text. A third gradient means the page has no focal surface left.
  3. **Verified at the ramp's worst point** — lightest stop in light theme, darkest in dark, never the midpoint, which flatters every gradient ever measured. Text over a gradient clears **7:1** there.

  Every `gradient(` in `globals.css` is declared in `frontend/__tests__/palette-contrast.test.ts` with whether text sits on it; an undeclared one fails the suite. The prior **named exception** stands and is registered as text-free: the ambient ground wash on `body::before` (two ≤5%-alpha radials, fixed to the viewport), which exists so translucent chrome has something behind it to blur. *(That exception was itself an amendment, 2026-07-26, for "a little glass look".)*
- **Don't** ship sci-fi copy — write plainly: "Loading…", "No conflicts pending review."
- **Don't** hardcode off-token hex or palette-step colors in components.
- **Don't** use a `border-left`/`border-right` >1px as a colored accent stripe; use full hairlines or background tints.
- **Don't** nest cards.
