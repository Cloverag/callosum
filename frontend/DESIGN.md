---
name: Meridian Board OS
description: Calm, provenance-first institutional-memory interface for startup boards — dual-theme zinc surface, one violet accent, restrained glass.
colors:
  accent: "#7c3aed"
  accent-foreground: "#ffffff"
  accent-emphasis: "#a78bfa"
  success: "#15803d"
  warning: "#d97706"
  danger: "#dc2626"
  info: "#2563eb"
  foreground: "#fafafa"
  muted-foreground: "#a1a1aa"
  subtle-foreground: "#71717a"
  border: "#ffffff1f"
  border-strong: "#ffffff38"
  focus: "#a78bfa"
  surface: "#09090b"
  surface-elevated: "#18181b"
  surface-raised: "#27272a"
  surface-sunken: "#050506"
  surface-glass: "#18181bb8"
typography:
  headline:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.875rem"
    fontWeight: 300
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 500
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
  caption:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "normal"
  label:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.625rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "0.1em"
rounded:
  sm: "4px"
  md: "8px"
  lg: "12px"
  xl: "16px"
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
    rounded: "{rounded.md}"
    padding: "10px 24px"
    typography: "{typography.body}"
  button-ghost:
    backgroundColor: "{colors.surface-elevated}"
    textColor: "{colors.muted-foreground}"
    rounded: "{rounded.md}"
    padding: "10px 24px"
    typography: "{typography.body}"
  input-search:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.full}"
    padding: "6px 16px 6px 36px"
    typography: "{typography.body}"
  badge:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.sm}"
    padding: "4px 12px"
    typography: "{typography.label}"
  card:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.xl}"
    padding: "24px"
  nav-item:
    backgroundColor: "{colors.surface-elevated}"
    textColor: "{colors.muted-foreground}"
    rounded: "{rounded.md}"
    padding: "10px 12px"
    typography: "{typography.body}"
---

# Design System: Meridian Board OS

## 1. Overview

**Creative North Star: "The Quiet Situation Room"**

Meridian is where a founder walks in the hour before a board meeting and instantly trusts what they see. The interface is a calm, low-light situation room: a deep slate surface, one disciplined blue accent, and hairline structure that lets dense governance information — decisions, evidence, provenance, access — sit legibly side by side without shouting. It is dual-theme (a deep near-black dark mode and a cool slate-grey light mode) because these users work in every ambient condition, from a dim boardroom to a bright home office. The system's job is to disappear into the task and make the *record* the hero.

This system evolves an earlier, more cinematic treatment (heavy glass, accent glow, sci-fi voice) toward earned executive confidence. Glass and depth remain in the vocabulary but as **restraint, not spectacle**: a panel separates a toolbar from content, it does not perform. The palette explicitly rejects the things this product is not — the dated weight of enterprise board portals (Diligent, Boardvantage), the gradient hero-metric tiles and identical card grids of generic SaaS dashboards, crypto/fintech neon, and decoration-over-density productivity apps with oversized cards, oversized icons, and wasteful whitespace. Trust here is legibility under scrutiny, not atmosphere.

**Key Characteristics:**
- Dual-theme slate system: deep near-black dark, cool slate-grey light — both first-class.
- Exactly one accent (a single blue), reserved for state, selection, and provenance — never decoration.
- Hairline dividers and restrained glass carry structure; density beats whitespace.
- Inter throughout, light-weight headings against small tracked labels for hierarchy without noise.
- WCAG 2.2 AA is a hard floor — every text/surface pairing must pass 4.5:1.

**Density doctrine.** Meridian is dense but calm — never "minimal." Optimize for seeing more meaningful information without overwhelming the user; reduce decorative elements before reducing content. Whitespace and ornament yield to legible, tight information; decoration is the first thing cut, content the last.

**Motion hierarchy.** Motion is tiered and must not creep into every interaction:
- **L0 — None:** static content, tables at rest, anything being scanned.
- **L1 — Hover / press (100–150ms):** state feedback on interactive elements (`--duration-hover`).
- **L2 — Page & state transitions (180–250ms):** route changes, dialog/popover open-close, list reflow (`--duration-state` + `--ease-out-quart`).
- **L3 — Hero moments:** landing and empty states only — never inside a working surface.
- **Reduced motion:** all non-essential motion removed; transitions collapse to instant/crossfade (enforced globally in `globals.css`).

## 2. Colors

A restrained dual-theme slate palette expressed as **semantic tokens, not palette steps**: components reference roles (`accent`, `surface-raised`, `muted-foreground`), never a raw hex or a `blue-500`. Near-neutral surfaces are layered by lightness, one blue accent carries interaction, and four status hues cover system state. Every pairing below is verified to WCAG 2.2 AA. The dark theme is canonical (the situation room); the light value follows in each entry.

### Primary
- **Accent — Signal Blue** (fill `#2563eb`; on-accent label `#ffffff`; as-text `accent-emphasis` dark `#60a5fa` / light `#2563eb`; wash `accent-subtle`): The one interactive color. `accent` fills the primary button and the current selection; `accent-emphasis` writes focus, active nav, and state/provenance indicators. Two sub-roles because a single blue cannot be both an AA-safe button fill *and* AA-safe small text on a near-black surface — `accent` fills, `accent-emphasis` writes. Never decoration.

### Status
- **Success** (`#15803d`, emphasis dark `#4ade80`), **Warning** (`#d97706` with a dark label, emphasis dark `#fbbf24`), **Danger** (`#dc2626`, emphasis dark `#f87171`), **Info** (`#2563eb`, emphasis dark `#60a5fa`): Each ships a solid (badges/fills), a `-foreground` (label on the solid), an `-emphasis` (AA text/icon on a surface), and a `-subtle` (wash). For meeting status, review outcomes, and system feedback — state, never decoration.

### Neutral
Tonal elevation, base upward: **Surface** (base; dark `#020617` / light `#e2e8f0`), **Surface-elevated** (panels, toolbars, sidebar; dark `#0f172a` / light `#f1f5f9`), **Surface-raised** (cards, dialogs, popovers; dark `#1e293b` / light `#ffffff`), **Surface-sunken** (inset wells, quote blocks; dark `#010409` / light `#cbd5e1`), and **Surface-glass** (blurred shell/overlay only; dark `rgba(15,23,42,0.72)` / light `rgba(248,250,252,0.72)`).
- **Text** / `foreground` (dark `#f8fafc` / light `#0f172a`): Primary text and headings.
- **Text-muted** / `muted-foreground` (dark `#94a3b8` / light `#475569`): Secondary text, labels, timestamps. Light is slate-600, AA-verified on every surface (the earlier slate-500 failed and was corrected).
- **Subtle** / `subtle-foreground` (`#64748b`): Large or decorative text only — never body.
- **Border** (dark `rgba(255,255,255,0.12)` / light `rgba(15,23,42,0.12)`), plus **Border-strong** for emphasis: Hairline separators. Never a heavy or colored stripe.
- **Focus** (dark `#60a5fa` / light `#2563eb`): The focus-ring color; ≥3:1 against its surface.

### Named Rules
**The Semantic-Only Rule.** Components consume semantic tokens exclusively. A raw hex, a `blue-500`, or a `slate-800` inside a component is a bug — it breaks theming and AA at once.

**The One Signal Rule.** The accent family appears on ≤10% of any screen — primary action, selection, focus, and state/provenance. A blue used to "brighten up" a panel is a bug.

**The Slate-Not-Paper Rule.** Light mode is cool slate (`#e2e8f0`), never warm paper/cream. The calm comes from neutral slate, not tint.

## 3. Typography

**Body & Display Font:** Inter (with `ui-sans-serif, system-ui, sans-serif` fallback)

**Character:** One family, tuned across weights. Light-weight (300) headings give calm authority; the workhorse body sits at 400; small labels go semibold with wide tracking. No display face, no pairing — a product UI earns hierarchy through weight and size, not font contrast.

### Hierarchy
- **Headline** (300, 1.875rem / `text-3xl`, line-height ~1.15, tracking -0.02em): Page/section titles ("Entity Conflicts"). The signature light-weight heading.
- **Title** (500, 1.25rem / `text-xl`, line-height ~1.3): Object names, panel titles, entity names in review cards.
- **Body** (400, 0.875rem / `text-sm`, line-height 1.6): The default. Descriptions, quotes, table cells. Prose capped at 65–75ch; dense data may run wider.
- **Caption** (400, 0.75rem / `text-xs`): Dense metadata — meeting times, day numbers, counts, secondary text in tight UI (calendar cells, small buttons). The density tier.
- **Label** (600, 0.625rem / `text-[10px]`, tracking 0.1em, uppercase): Metadata eyebrows — "SIMILARITY", "SOURCE CONTEXT", status chips. Deliberately tiny and tracked.

### Named Rules
**The Fixed-Scale Rule.** Type is a fixed rem scale, never fluid `clamp()`. Users view at consistent DPI inside an app shell; a heading that shrinks in a sidebar is a regression, not responsiveness.

**The Quiet-Label Rule.** Uppercase tracked labels are for true metadata only (status, provenance, similarity). They are never section eyebrows above every block — that is SaaS grammar this system rejects.

## 4. Elevation

A hybrid system that is **flat by default and layered by role**. Depth comes primarily from tonal layering — base → panel → card surfaces stepped by lightness — not from heavy drop shadows. Shadows are soft and ambient, used to lift chrome (sidebar, header) and interactive surfaces off the page, never to make every card float. The restrained glass treatment (a blurred translucent panel with a hairline border and a 1px inner highlight) is reserved for the app shell and true overlays.

### Shadow Vocabulary
- **Panel shadow** (light `0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03)`; dark `0 10px 30px rgba(0,0,0,0.5)`): The glass-panel elevation for sidebar, header, and card shells, paired with an `inset 0 1px 0` highlight.
- **Accent glow** (`0 0 20px` of accent-glow): A focused halo used *sparingly* around a single active/critical affordance. Not a default card treatment.

### Named Rules
**The Tonal-First Rule.** Depth is layered lightness first (base/panel/card), shadow second. If a surface reads as elevated without a shadow, it needs no shadow.

**The Glass-Is-Structural Rule.** Backdrop-blur glass is reserved for the app shell (sidebar, header) and overlays. Glass on every content card is prohibited — it is the cinematic reflex this system is retiring.

## 5. Components

The vocabulary is refined and restrained: hairline borders, `md`–`xl` radii, quiet defaults that respond crisply to state. Every interactive component ships all of default, hover, focus-visible, active, disabled, and (where it loads) loading.

### Buttons
- **Shape:** Gently rounded (`8px` / `rounded-lg`).
- **Primary:** Accent fill (`accent`) with the on-accent label (`accent-foreground`); padding `10px 24px`; body-size medium weight. The single most important action per surface. (This replaces the earlier contrast-ink primary — the accent is now the one interactive fill, keeping the system to a single signal color.)
- **Ghost / Secondary:** Transparent on panel, muted-ink label, hairline border; hover raises to a faint `5%` ink wash and full-ink label.
- **Hover / Focus:** 150–250ms color/opacity transition. Focus-visible shows a 2px accent ring at ≥3:1 — never color-only. The legacy `.cinematic-button` shimmer sweep is deprecated (see Don'ts).

### Chips / Badges
- **Style:** Card-surface fill, hairline border, tiny uppercase tracked label; used for entity type, status, and clearance.
- **State:** Neutral by default; the accent tint appears only on an active/selected or attention state (e.g. "pending review"), never on inert metadata.

### Cards / Containers
- **Corner Style:** `16px` (`rounded-2xl`) for primary review cards; `12px` for nested blocks.
- **Background:** Panel surface for the shell, card surface for raised/nested content.
- **Shadow Strategy:** Tonal-first (see Elevation); soft panel shadow only on the outer shell.
- **Border:** Always a hairline divider; never a colored side-stripe.
- **Internal Padding:** `24px`–`32px` on primary cards; tighten for dense list rows.

### Inputs / Fields
- **Style:** Card-surface fill, hairline border, `full`-radius for search, `md` for form fields; leading icon in muted ink.
- **Focus:** Border shifts to a brighter hairline plus a 1px accent ring — a border shift, not a glow bloom.
- **Error / Disabled:** Error uses a dedicated red token (to be added — the system currently has no semantic error/warning/success colors); disabled drops to `50%` and removes pointer affordance.

### Navigation (Sidebar)
- **Style:** Panel-surface glass rail, `256px` wide. Nav items are body-size, muted-ink at rest.
- **States:** Hover raises label to full ink on a faint ink wash; **active** shows a `10%` primary wash, an accent icon, and an inset top highlight. Active state must be derived from the current route, not hardcoded (see Don'ts).

### Signature Component — Provenance Card
The entity-conflict / evidence review card is the system's signature surface: paired source contexts, a similarity chip, exact source quotes in bordered quote blocks, and a first-class Approve / Reject action row. It embodies the product's "provenance is visible, human holds the pen" principles — every fact shows its source and every consequential action is an explicit, unmistakable button.

## 6. Do's and Don'ts

### Do:
- **Do** keep Signal Blue (`#3b82f6`) to ≤10% of any screen — state, selection, focus, and provenance only.
- **Do** darken light-mode Muted Ink from `#64748b` to at least `#475569` (slate-600) so secondary text clears 4.5:1 on light base and card surfaces. Verify every text/surface pair against AA; a surface that can't pass contrast is redesigned, not shipped.
- **Do** convey depth by tonal layering (base → panel → card) first, shadow second.
- **Do** derive nav/tab active state from the current route (`usePathname`), so every page highlights correctly.
- **Do** give every interactive element a visible, non-color-only focus ring and a full keyboard path; make citation/source interactions keyboard-operable.
- **Do** provide a `prefers-reduced-motion` alternative (crossfade or instant) for every transition, and keep state transitions in the 150–250ms range.
- **Do** add semantic state tokens (error / warning / success / info) before building forms and status surfaces — they are currently missing.
- **Do** keep information density high: tight, legible rows and short paths to common actions.

### Don't:
- **Don't** style like an enterprise board portal (Diligent, Boardvantage) — heavy chrome, dated compliance-software weight.
- **Don't** style like a generic SaaS dashboard — no gradient hero-metric tiles, no identical icon-heading-text card grids, no template admin theming.
- **Don't** use crypto/fintech neon — no dark-mode neon, saturated purple-to-blue gradients, or trading-terminal flash.
- **Don't** prioritize decoration over density — no oversized cards, oversized icons, excessive whitespace, or layouts that force scrolling for common tasks.
- **Don't** use glass (backdrop-blur) on content cards or glow as a default — glass is structural (shell/overlays only); the accent glow is a rare, single-affordance halo.
- **Don't** ship sci-fi copy — no "Initializing neural matrix…", "System optimal", or "neural" theatrics. Write plainly: "Loading…", "No conflicts pending review."
- **Don't** hardcode off-token hex colors in components (e.g. `text-[#d4e4fa]`, `text-[#8691a7]`); use the semantic tokens so both themes and AA hold.
- **Don't** use a `border-left`/`border-right` greater than 1px as a colored accent stripe on cards, list items, or callouts; use full hairline borders or background tints.
- **Don't** signal state with color alone; pair it with an icon, label, or shape.
