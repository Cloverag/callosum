---
name: Meridian Board OS
description: Calm, provenance-first board operating system — neutral light surface, one blue action color, violet reserved for institutional memory.
colors:
  accent: "#2563eb"
  accent-foreground: "#ffffff"
  accent-hover: "#1d4ed8"
  accent-emphasis: "#1d4ed8"
  accent-subtle: "#eff6ff"
  accent-border: "#bfdbfe"
  success: "#16a34a"
  success-emphasis: "#15803d"
  warning: "#f59e0b"
  warning-emphasis: "#b45309"
  danger: "#ef4444"
  danger-emphasis: "#dc2626"
  info: "#2563eb"
  memory: "#6d28d9"
  memory-emphasis: "#6d28d9"
  memory-soft: "#8b5cf6"
  foreground: "#111827"
  muted-foreground: "#475569"
  subtle-foreground: "#64748b"
  border: "#e5e7eb"
  border-strong: "#cbd5e1"
  focus: "#2563eb"
  surface: "#f7f8fa"
  surface-elevated: "#ffffff"
  surface-raised: "#ffffff"
  surface-alt: "#f8fafc"
  surface-sunken: "#f1f5f9"
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

This is a **light-mode-first** product (a single, deliberately tuned light palette). The palette explicitly rejects what this product is not: the dated weight of enterprise board portals (Diligent, Boardvantage), the gradient hero-metric tiles and identical card grids of generic SaaS dashboards, crypto/fintech neon, and decoration-over-density productivity apps with oversized cards and wasted whitespace. Trust here is legibility under scrutiny, not atmosphere.

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

A restrained light palette expressed as **semantic tokens, not palette steps** — components reference roles (`accent`, `surface-raised`, `muted-foreground`, `memory-emphasis`), never a raw hex or a `blue-600`. Every pairing below is verified to WCAG 2.2 AA.

### Action — Blue (`#2563EB`)
The one interactive color. `accent` fills the primary button and selected state; `accent-hover` (`#1D4ED8`) is the hovered fill; `accent-emphasis` (`#1D4ED8`) writes accent-as-text and icons (AA on white and on the soft-blue wash); `accent-subtle` (`#EFF6FF`) is the active-nav / selected-row wash; `accent-border` (`#BFDBFE`) its hairline. **Used only for action** — buttons, active navigation, links, focus rings, selected tabs, checkboxes, calendar events. Never for success/warning, never decoration.

### Status
Each ships a solid (fills/dots), a `-foreground` (label on the solid), an `-emphasis` (AA text/icon on a surface), and a `-subtle` (wash).
- **Success — Green `#16A34A`** (emphasis `#15803D`): verified, completed, approved, healthy.
- **Warning — Amber `#F59E0B`** (foreground `#78350F` on the amber fill; emphasis `#B45309`): pending review, draft, awaiting approval.
- **Danger — Red `#EF4444`** (emphasis `#DC2626`): errors, overdue, failed, quarantined, destructive actions.
- **Info** maps to the action blue — informational status shares the one blue.

### Institutional Memory — Violet (`#6D28D9`)
The product's identity color, **reserved for institutional-memory surfaces only**: graph health, the verified-share gauge, provenance, memory metrics, and memory trend charts. `memory-emphasis` (`#6D28D9`, ~6.6:1 on white) writes text/icons and draws the gauge/sparkline; `memory-soft` (`#8B5CF6`) is for large/secondary graph elements; `memory-subtle` a faint wash. **Never a button, never navigation** — that is what makes it read as *memory* and gives Meridian a unique identity.

### Neutral
Tonal elevation, base upward: **Surface** (page base `#F7F8FA`), **Surface-elevated** (sidebar, header, AI rail, panels — `#FFFFFF`), **Surface-raised** (cards, dialogs, popovers — `#FFFFFF`), **Surface-alt** (secondary/nested panel `#F8FAFC`), **Surface-sunken** (inset wells, quote blocks, input fill — `#F1F5F9`).
- **Text / `foreground`** `#111827`: primary text and headings.
- **Text-muted / `muted-foreground`** `#475569` (slate-600): secondary text, labels, timestamps. AA on every surface.
- **Subtle / `subtle-foreground`** `#64748b` (slate-500): large or decorative text only — never body.
- **Border** `#E5E7EB`, **Border-strong** `#CBD5E1`: hairline separators. Never a heavy or colored stripe.
- **Focus** `#2563EB`: the focus-ring color; a 2px ring, ≥3:1 against its surface.

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

### Registry components

Third-party shadcn registries are available — **KokonutUI** (`@kokonutui`), **Animate UI** (`@animate-ui`), and **Bklit UI** (`@bklit`) for charts. They are configured in `components.json` and install into `src/components/vendor/`, never into `ui/`: `ui/` is the design system and the CLI must not be able to overwrite it.

Registry source is written in shadcn's token vocabulary, not ours. `src/app/shadcn-compat.css` maps that vocabulary onto our semantic tokens (`background`→`surface`, `card`→`surface-raised`, `primary`→`accent`, `muted`→`surface-sunken`, `ring`→`focus`, …), so a vendored component inherits Meridian colour without edits. This does not weaken the Semantic-Only rule — the bridge contains no hex and no palette steps, only aliases to tokens `globals.css` already owns.

**One token cannot be bridged: `accent`.** shadcn means a subtle hover surface; we mean ACTION blue, and shipped components depend on our meaning. `npm run retoken` rewrites the shadcn sense (`bg-accent`→`bg-surface-sunken`, `text-accent-foreground`→`text-foreground`) plus the radius utilities (`rounded-lg`→12px, `rounded-xl`→16px) in vendored files only. **Run it after every `shadcn add`** — skipping it renders vendored hover states as solid blue bars.

**Charts.** `chart-1…5` is a *sequential violet ramp* scoped to memory surfaces, because violet is reserved for Institutional Memory and blue for action — a generic categorical rainbow is not available to us. For non-memory charts (e.g. meeting mix by status) use the status tokens directly; they already carry the right meaning. A categorical palette for genuinely unordered non-memory series is an **open decision**, not something to improvise per chart.

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
- **Don't** use gradients, neon, glow-as-default, or glass on content cards.
- **Don't** ship sci-fi copy — write plainly: "Loading…", "No conflicts pending review."
- **Don't** hardcode off-token hex or palette-step colors in components.
- **Don't** use a `border-left`/`border-right` >1px as a colored accent stripe; use full hairlines or background tints.
- **Don't** nest cards.
