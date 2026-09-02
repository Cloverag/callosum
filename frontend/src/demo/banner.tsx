import { DEMO_ENABLED } from "./mode";
import { DEMO_WORKSPACE_ID } from "./fixtures/ids";

/**
 * The bar that says the data on screen is fabricated.
 *
 * ---------------------------------------------------------------------------
 * WHY IT IS COUPLED TO THE INTERCEPTOR AND NOT TO ITS OWN ENV READ
 * ---------------------------------------------------------------------------
 * It imports `DEMO_ENABLED` — the same binding `transport` branches on, from
 * the same module, resolved from one read of the variable. It does not read
 * `process.env` itself. Two independent reads of one variable is precisely how
 * a build ends up serving fixtures with the banner off, and a demo mode whose
 * warning can be absent while its fabrication is present is worse than no demo
 * mode: it is the `lib/api.ts` failure with extra steps.
 *
 * `__tests__/demo-mode.test.ts` asserts the coupling structurally — that
 * `NEXT_PUBLIC_MERIDIAN_DEMO` is named exactly once in `src/` — rather than
 * asserting that the banner happens to render when demo mode happens to be on.
 *
 * ---------------------------------------------------------------------------
 * WHY THE COLOURS ARE LITERAL AND NOT TOKENS
 * ---------------------------------------------------------------------------
 * Every other surface reads the OKLCH palette from `globals.css`, and should.
 * This one does not. A token is a value someone can retune, and the failure
 * mode of retuning this one — a warning that has quietly become low-contrast,
 * or the same colour as the chrome behind it — is that fabricated data is on
 * screen without the notice that makes it honest. It is a safety device, so it
 * is deliberately not themeable. That is also why it is not a badge, a corner
 * pill or a tooltip: it spans the viewport, it is above the shell, and it does
 * not scroll away.
 *
 * Returning `null` when demo mode is off means the element costs an unset build
 * nothing, and `layout.tsx` mounts it unconditionally rather than carrying a
 * condition of its own — one place decides.
 */
export function DemoBanner() {
  if (!DEMO_ENABLED) return null;

  return (
    <div
      /*
        The hook `globals.css` keys the shell's height off
        (`body:has([data-demo-banner])`). An attribute rather than a class so it
        cannot be mistaken for styling and removed as unused, and so the height
        rule stays inert in a normal build: this component returns null, the
        attribute never reaches the DOM, and the selector matches nothing.
      */
      data-demo-banner=""
      role="status"
      aria-live="polite"
      style={{
        position: "sticky",
        top: 0,
        zIndex: 9999,
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        justifyContent: "center",
        gap: "0.25rem 0.75rem",
        padding: "0.5rem 1rem",
        background: "#7f1d1d",
        color: "#fff5f5",
        borderBottom: "2px solid #fca5a5",
        font: "600 0.8125rem/1.4 system-ui, sans-serif",
        letterSpacing: "0.01em",
        textAlign: "center",
      }}
    >
      <span aria-hidden="true">&#9888;</span>
      <span>
        DEMO MODE — every figure, name and date below is <strong>fabricated</strong>. Nothing
        here was measured, and no backend is being read.
      </span>
      <span style={{ opacity: 0.75, fontWeight: 400, fontVariantNumeric: "tabular-nums" }}>
        workspace {DEMO_WORKSPACE_ID}
      </span>
    </div>
  );
}
