/**
 * The motion scale, mirrored for JavaScript.
 *
 * `globals.css` is the source of truth: it declares one ease and four duration
 * tiers as tokens, exactly as it declares colour. CSS animations read them
 * directly. Framer Motion cannot — it animates inline styles from JS and has no
 * access to a custom property — so the same values are restated here.
 *
 * A mirror that nothing checks is just a second place to be wrong, which is what
 * this file replaces. Before it, five durations (0.12 / 0.2 / 0.35 / 1.1) and
 * TWO rival ease curves were spread across six components while `DESIGN.md`
 * published a hierarchy of two durations and one ease. `session-gate.tsx` and
 * `needs-you.tsx` used `[0.22, 1, 0.36, 1]`; `AssistantRail.tsx` used
 * `[0.16, 1, 0.3, 1]`, which is the curve the token layer actually declares.
 * Nobody chose to have two — they accumulated.
 *
 * `__tests__/motion-contract.test.ts` parses `globals.css` and asserts every
 * value below matches its token, and that no component writes a duration or an
 * ease of its own. Same idiom as `palette-contrast.test.ts`: a documented
 * invariant becomes an enforced one.
 *
 * Seconds, because that is the unit Framer takes. The CSS tokens are in ms.
 */

/** The one ease — `--ease-out-quart`, `cubic-bezier(0.16, 1, 0.3, 1)`. */
export const EASE = [0.16, 1, 0.3, 1] as const;

/**
 * The four tiers of the motion hierarchy (DESIGN.md §1). A component picks a
 * tier; it does not pick a number.
 *
 * · `hover`    L1 — state feedback on an interactive element.
 * · `state`    L2 — a dialog opening, a list reflowing, a progress fill.
 * · `entrance` L4 — a band or a card arriving once, on load. Longer than a state
 *                   change because it travels further: 10px, not 2px.
 * · `reveal`   L5 — a measured figure drawing itself: the gauge sweep, the
 *                   sparkline draw, a distribution bar growing. The value is the
 *                   gauge's, which shipped and was reviewed at 1.1s; the tier was
 *                   named around it rather than retuned to accommodate new members.
 */
export const DURATION = {
  hover: 0.12,
  state: 0.2,
  entrance: 0.4,
  reveal: 1.1,
} as const;

/**
 * The beat between staggered siblings. 50ms is the value `needs-you.tsx` already
 * shipped; it is promoted to a token rather than replaced, because nothing was
 * measured that said it was wrong.
 */
export const STAGGER = 0.05;

/**
 * A transition for one tier, already reduced-motion aware.
 *
 * The global `prefers-reduced-motion` rule in `globals.css` collapses CSS
 * transition and animation durations, but it cannot touch Framer: those
 * animations run in JS on inline styles and never consult a media query. Every
 * Framer call site therefore has to branch itself, and half of them forgot —
 * `entity-conflicts/page.tsx` branched its transforms and then animated for a
 * full 350ms anyway.
 */
export function transition(tier: keyof typeof DURATION, reduce: boolean | null) {
  return { duration: reduce ? 0 : DURATION[tier], ease: EASE };
}
