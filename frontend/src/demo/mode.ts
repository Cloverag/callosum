/**
 * Whether the application is answering from fixtures instead of from the API.
 *
 * ---------------------------------------------------------------------------
 * WHY THE CHECK IS THIS STRICT
 * ---------------------------------------------------------------------------
 * The obvious spelling — `Boolean(process.env.NEXT_PUBLIC_MERIDIAN_DEMO)` — is
 * true for `"0"`, `"false"`, `"off"` and `"no"`, because those are non-empty
 * strings. An operator who set the variable to `0` to turn demo mode *off*
 * would turn it on. That failure is silent and it fabricates data, which is the
 * one class of failure this whole feature is built to be incapable of.
 *
 * So: exactly the string `"1"`, and nothing else. Unset, empty, `"0"`, `"true"`,
 * `"TRUE"`, `" 1"` are all off. `"true"` being off is deliberate rather than an
 * oversight — one spelling that works is easier to reason about than five, and a
 * variable that silently ignores a plausible value is better than one that
 * silently accepts an implausible one.
 *
 * `NEXT_PUBLIC_` is required for the value to exist in the browser at all: Next
 * inlines only that prefix into client bundles. Without it the constant would be
 * `undefined` client-side and demo mode would appear to do nothing, which is a
 * confusing way to be safe.
 */

/** True only for the exact string `"1"`. Exported so a test can drive it directly. */
export function isDemoValue(value: string | undefined): boolean {
  return value === "1";
}

/**
 * Resolved once, at module load.
 *
 * Read as a whole literal rather than as `process.env[NAME]`: Next's inlining is
 * a build-time textual substitution of `process.env.NEXT_PUBLIC_MERIDIAN_DEMO`,
 * and a computed lookup is not substituted — it would read `undefined` in the
 * browser however the variable was set.
 */
export const DEMO_ENABLED = isDemoValue(process.env.NEXT_PUBLIC_MERIDIAN_DEMO);
