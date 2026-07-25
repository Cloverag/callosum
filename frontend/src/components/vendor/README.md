# `vendor/` — components copied in from shadcn registries

Everything in this directory was installed by the shadcn CLI from a third-party
registry (KokonutUI, Animate UI, Bklit UI). It is **vendored source we own**, not
a dependency — edit it freely.

It is deliberately *not* `src/components/ui/`. That directory holds the
hand-authored Meridian primitives (Button, Card, Badge, Dialog, Gauge, …), and
`components.json` points the CLI's `ui` alias here so that
`npx shadcn@latest add button` can never overwrite them.

## Adding a component

```bash
npx shadcn@latest add @animate-ui/tooltip     # animated Radix primitives
npx shadcn@latest add @kokonutui/particle-button
npx shadcn@latest add @bklit/area-chart       # charts
npm run retoken                               # ← always, see below
```

## Why `retoken` is not optional

Registry source is written against shadcn's token vocabulary. Most of it is
mapped onto Meridian's semantic tokens declaratively in
`src/app/shadcn-compat.css`, so `bg-background`, `bg-card`, `bg-primary`,
`text-muted-foreground`, `border-input`, and `ring` all just work.

Two things cannot be bridged that way, and `scripts/retoken.mjs` fixes them:

| shadcn writes | Meridian means | Rewritten to |
|---|---|---|
| `bg-accent` | ACTION blue, not a hover wash | `bg-surface-sunken` |
| `text-accent-foreground` | white-on-blue label | `text-foreground` |
| `rounded-lg` | stock 8px, brief says 12px | `rounded-[12px]` |
| `rounded-xl` | stock 12px, brief says 16px | `rounded-[16px]` |

`accent` is the important one. shadcn uses it for subtle hover surfaces;
Meridian uses it for the solid blue of a primary button, and 18 shipped call
sites depend on that meaning. Skipping `retoken` renders every vendored menu
hover as a solid blue bar.

`npm run retoken:check` reports without writing and exits non-zero if work
remains — use it if you want this in CI.

## What belongs here vs. `ui/`

- A vendored component stays here **as-is** if it is used directly.
- If it becomes load-bearing across the app, promote it: move it to `ui/`,
  strip the registry's variant API down to what Meridian actually uses, and
  document it in `DESIGN.md`. Promotion is a deliberate act, not a default —
  `ui/` is the design system, and everything in it should be defensible.
