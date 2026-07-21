# Design System Audit — Meridian Frontend

Snapshot of the existing `feat/frontend-design-system` code measured against [DESIGN.md](./DESIGN.md), [PRODUCT.md](./PRODUCT.md), and the WCAG 2.2 AA hard floor. Findings are ordered by severity. Each is an **evolution** of the established aesthetic, not a replacement — the slate surface, one-accent discipline, and restrained-glass DNA are kept.

Severity: **P0** breaks a hard requirement (a11y floor, broken surface, functional bug) · **P1** violates a documented system rule · **P2** polish / gap to close before scale.

---

## P0 — must fix

### 1. Light-mode secondary text fails AA contrast
`globals.css` `--muted-foreground: #64748b` (slate-500) on `--background: #e2e8f0` ≈ **3.5:1**, and on `--card-bg: #f8fafc` ≈ **4.0:1** — both below the 4.5:1 body floor. Used for every timestamp, label, and description in light mode.
**Fix:** darken to `#475569` (slate-600, ~5.9:1 on base) or `#334155`. Re-verify all light-mode muted pairings.

### 2. Root route is create-next-app boilerplate
`src/app/page.tsx` is the untouched Next.js template (Next/Vercel logos, "edit page.tsx", external Deploy/Docs links, off-token `bg-zinc-50 dark:bg-black`). It is the app's `/` and shares none of the design system.
**Fix:** replace with a redirect to `/dashboard` (or a real landing) using the token system.

### 3. Stub pages ship off-token hardcoded colors
`dashboard`, `documents`, `meetings`, `settings` are one-line "under construction" stubs using hardcoded hex `text-[#d4e4fa]` / `text-[#8691a7]` that bypass the token system and won't theme or pass AA.
**Fix:** build them on the token/primitive layer (see plan); never hardcode hex.

### 4. Sidebar active state is hardcoded
`Sidebar.tsx`: `const isActive = item.name === 'Entity Conflicts'`. Every route will highlight "Entity Conflicts" regardless of where the user is — a functional bug the moment a second page exists.
**Fix:** derive from `usePathname()`.

---

## P1 — violates a documented rule

### 5. Glass used as a default surface, not structurally
`.glass-panel` (backdrop-blur) is applied to the shell (sidebar, header) *and* to every content card in `entity-conflicts/page.tsx`. Violates the **Glass-Is-Structural Rule** and Impeccable's glassmorphism ban.
**Fix:** keep glass on shell + overlays only; content cards use the tonal `card` surface.

### 6. Glow-as-default
`.text-glow` / `.text-glow-accent` on headings and `shadow-[0_0_20px_var(--color-accent-glow)]` on cards make glow a default treatment. Violates the calm-trust direction and the **One Signal Rule**.
**Fix:** remove default text-glow; reserve the accent halo for a single active/critical affordance.

### 7. Second accent (purple) off-palette
`entity-conflicts/page.tsx` renders Entity B's quote stripe as `bg-purple-500`. Introduces a second accent not in the token system — breaks the **One Signal Rule**.
**Fix:** use the neutral hairline for both; distinguish A/B by label/position, not a new hue.

### 8. Colored side-stripes on quote blocks
Quote blocks use `absolute … w-1 h-full bg-accent/20` — a 4px colored left stripe, the exact side-stripe pattern DESIGN.md and Impeccable ban.
**Fix:** full hairline border or a faint background tint; no >1px colored edge stripe.

### 9. Sci-fi copy contradicts the product voice
"Initializing neural matrix…", "System optimal", "neural matrix" clash with PRODUCT.md's "precise, calm, plain" voice.
**Fix:** "Loading…", "No conflicts pending review", etc.

---

## P2 — gaps to close before scaling

### 10. No semantic state tokens
The palette has no `error` / `warning` / `success` / `info` / `disabled` roles. Required before forms, status surfaces, and the approve/reject/return states scale.
**Fix:** add semantic tokens (both themes) at the token layer.

### 11. Focus indicators are weak / color-only-adjacent
Header search uses `focus:ring-glass-highlight` (near-white, likely <3:1); buttons rely on the browser default. AA needs a visible, non-color-only focus ring ≥3:1 on every interactive element.
**Fix:** standardize a 2px accent focus-visible ring primitive.

### 12. Loading uses text, not skeletons
The conflicts page shows a centered text string while loading. Product-register guidance prefers skeletons that preserve layout.
**Fix:** skeleton rows for list/table loads.

### 13. Off-token neutrals in components
`ThemeToggle.tsx` uses `text-neutral-500 dark:text-neutral-400` instead of `muted-foreground`. Minor drift that accumulates.
**Fix:** route all neutrals through tokens.

### 14. Redundant/decorative CSS to retire
`.cinematic-button` shimmer sweep is decorative motion that conveys no state (Product-register ban); the `.text-glow` light-mode variant is near-invisible.
**Fix:** remove `.cinematic-button`; fold any needed hover into the button primitive.

---

## Recommended remediation order

Bundle the fixes into the planned build so each layer lands clean:

1. **Token layer** — fix #1 (muted contrast), add #10 (semantic states), add #11 (focus ring), retire #6/#14 (glow/cinematic-button) at the source.
2. **Primitive layer** — Button, Badge, Input, Card, PageHeader, NavItem with full states; resolves #5, #7, #8, #11, #12, #13 by construction.
3. **Shell** — fix #4 (`usePathname` active state), confine glass to the shell (#5).
4. **Feature/content** — replace #2 (root) and #3 (stubs); rewrite the conflicts card copy (#9) on the new primitives.

Everything above preserves the slate + one-accent + restrained-glass identity; it removes the cinematic *reflexes* layered on top of it.
