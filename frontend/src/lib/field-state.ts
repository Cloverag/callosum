/**
 * The four states a *value* can be in that are not "here it is".
 *
 * ---------------------------------------------------------------------------
 * WHY THIS EXISTS
 * ---------------------------------------------------------------------------
 * `docs/ux/dashboard-content-spec.md` defines seven states every widget must
 * handle. Three of them — loading, empty, error — are *rendering* states, and
 * React gives them a structural home: `loading.tsx`, an empty branch, and
 * `error.tsx`. The other four are **data** states. They are properties of the
 * value itself, they survive a page reload, and no boundary can infer them.
 *
 * Before this file they were encoded as `T | null` and re-interpreted at each
 * call site. `memory-health.tsx` is the cautionary example: `pendingReview`
 * and `quarantined` were both `number | null`, and each rendered the em dash
 * and its explanation through a ternary that repeated the measured-case hint
 * in both branches. Four copies of the same reasoning, in one card. The next
 * surface to read those fields would have had to rediscover it, and the surface
 * after that would have printed `0`.
 *
 * The rule this encodes, from the spec:
 *
 *     A COUNT THAT WAS NEVER COUNTED IS NOT A ZERO.
 *
 * A `FieldState` cannot be rendered without deciding what to do about that,
 * because there is no numeric value to reach for until you have narrowed the
 * union.
 *
 * ---------------------------------------------------------------------------
 * WHY TWO UNIONS AND NOT ONE
 * ---------------------------------------------------------------------------
 * `not_measured` and `withheld` describe a scalar on a surface: a count, a
 * percentage, a name. `stale` and `locked` describe a whole governed object and
 * arrive from a mutation, not a read — a pack is locked, a decision is stale;
 * neither is a property of any single field on them. Collapsing all four into
 * one union would force every scalar to carry a version number it has no
 * business knowing. They are modelled separately for that reason.
 */

import { ApiError } from "@/lib/http";

/** Spec states 4 and 5, plus the ordinary case. */
export type FieldState<T> =
  | { readonly status: "measured"; readonly value: T }
  /** State 4. `reason` is required — an unexplained em dash is indistinguishable from a bug. */
  | { readonly status: "not_measured"; readonly reason: string }
  /**
   * State 5. The count is disclosed, the content is not.
   *
   * `count` is the whole disclosure: how many items this caller's clearance
   * excluded. Silent withholding is the failure the product exists to prevent,
   * and a title would leak the thing being withheld, so a number it is.
   */
  | { readonly status: "withheld"; readonly count: number };

export function measured<T>(value: T): FieldState<T> {
  return { status: "measured", value };
}

export function notMeasured<T>(reason: string): FieldState<T> {
  return { status: "not_measured", reason };
}

export function withheld<T>(count: number): FieldState<T> {
  return { status: "withheld", count };
}

/**
 * Bridges the `T | null` fields that already exist.
 *
 * Every `null` in `lib/insights.ts` carries a written justification in a comment
 * beside it; this is where that justification stops being a comment and becomes
 * a value the UI is obliged to render. Migration is per-field, so the two shapes
 * can coexist while surfaces are converted.
 */
export function fromNullable<T>(value: T | null | undefined, reason: string): FieldState<T> {
  return value === null || value === undefined ? notMeasured<T>(reason) : measured(value);
}

export function isMeasured<T>(
  state: FieldState<T>,
): state is { readonly status: "measured"; readonly value: T } {
  return state.status === "measured";
}

/**
 * Transforms a measured value, passing the other states through untouched.
 *
 * The point is that the callback cannot run on an unmeasured field, so a
 * formatter like `(n) => n.toLocaleString()` can never be handed a `null` and
 * can never quietly produce "0".
 */
export function mapMeasured<T, U>(state: FieldState<T>, fn: (value: T) => U): FieldState<U> {
  return state.status === "measured" ? measured(fn(state.value)) : state;
}

/**
 * Spec states 6 and 7, plus the ordinary case — properties of a governed object.
 */
export type ResourceState =
  | { readonly status: "editable" }
  /**
   * State 6. Someone else wrote first; a refetch may make the same write succeed.
   *
   * The version pair is carried through because it is the difference between
   * "someone else saved" and "someone else saved twice while you were typing",
   * and `ApiError.versions` deliberately returns `null` rather than inventing
   * numbers the server did not send — so these stay nullable here too.
   */
  | { readonly status: "stale"; readonly expected: number | null; readonly current: number | null }
  /**
   * State 7. The operation itself is refused and no amount of refetching helps:
   * a published pack, finalised minutes, an illegal transition.
   */
  | { readonly status: "locked"; readonly reason: string };

export const EDITABLE: ResourceState = { status: "editable" };

/**
 * Reads a resource state out of a failed request, or `null` if there isn't one.
 *
 * `null` is the important return. A 500, a network drop, an expired session —
 * none of those are states of the resource, and dressing them up as one would
 * tell the user their pack is locked when the truth is the server is down. Those
 * belong to state 3, which is `error.tsx`'s job.
 *
 * The 409-vs-422 split this leans on is already modelled on `ApiError`: a 409
 * means re-read and reconsider, a 422 means change something and resend.
 * `needsWorkspace` is a 409 too, and is deliberately excluded upstream by
 * `isUnretryableConflict` — it is handled by the session gate, not by a widget.
 */
export function resourceStateFromError(error: ApiError): ResourceState | null {
  if (error.isStale) {
    const versions = error.versions;
    return { status: "stale", expected: versions?.expected ?? null, current: versions?.current ?? null };
  }
  if (error.isUnretryableConflict) {
    return { status: "locked", reason: error.message };
  }
  return null;
}
