import { cn } from "@/lib/utils";
import { isMeasured, type FieldState, type ResourceState } from "@/lib/field-state";

/**
 * What an unmeasured field prints.
 *
 * An em dash rather than a zero, and never "0", "N/A" or "—%". The first is a
 * result, the second is filler, and the third implies a percentage was computed
 * and came out empty. This one says only "no value here", which is the truth.
 */
export const NOT_MEASURED = "—";

/**
 * Renders a `FieldState` without letting the unmeasured cases print as data.
 *
 * `format` only ever sees a measured value, so the ordinary formatting call —
 * `(n) => n.toLocaleString()` — cannot be reached with a `null` and cannot
 * produce a "0" for something nothing counted.
 *
 * The reason travels with the mark. An em dash on its own is indistinguishable
 * from a rendering bug, and the reader's next move is to ask why, so `title`
 * carries the explanation for a mouse and `aria-label` carries it for a screen
 * reader. The dotted underline follows the affordance already used for the
 * tooltip labels in `memory-health.tsx`, so "there is more to read here" looks
 * the same everywhere.
 */
export function FieldValue<T>({
  state,
  format,
  className,
}: {
  state: FieldState<T>;
  format?: (value: T) => string;
  className?: string;
}) {
  if (isMeasured(state)) {
    return <span className={cn("tabular-nums", className)}>{format ? format(state.value) : String(state.value)}</span>;
  }

  if (state.status === "withheld") {
    return (
      <span
        className={cn("tabular-nums text-muted-foreground", className)}
        title={`${state.count} withheld at your clearance. The answer may be incomplete.`}
        aria-label={`${state.count} withheld at your clearance. The answer may be incomplete.`}
      >
        {state.count} withheld
      </span>
    );
  }

  return (
    <span
      className={cn(
        "cursor-help text-subtle-foreground underline decoration-dotted decoration-border-strong underline-offset-4",
        className,
      )}
      title={`Not measured — ${state.reason}`}
      aria-label={`Not measured — ${state.reason}`}
    >
      {NOT_MEASURED}
    </span>
  );
}

/**
 * Builds the tooltip text for a field, so the measured explanation is written once.
 *
 * The shape this replaces looked like:
 *
 *     hint={x === null ? "<what it means>. Not measured because ..." : "<what it means>."}
 *
 * — which duplicates the definition of the metric across both branches of a
 * ternary, in every widget that shows it. When the definition is later reworded,
 * one branch gets updated and the other keeps the old wording for exactly the
 * readers who see the unmeasured case.
 */
export function fieldHint<T>(state: FieldState<T>, meaning: string): string {
  if (state.status === "not_measured") return `${meaning} Not measured — ${state.reason}`;
  if (state.status === "withheld") {
    return `${meaning} ${state.count} withheld at your clearance; the figure shown may be incomplete.`;
  }
  return meaning;
}

/**
 * The banner a governed object shows when the *state* refused a well-formed write.
 *
 * Deliberately not an error: nothing broke. Stale offers the retry, because a
 * refetch genuinely may let the same write through; locked does not, because
 * offering "try again" on a refusal that can never succeed invites the user to
 * resend an identical request forever. Locked says why instead — a pack that is
 * simply greyed out with no explanation is the same dead end as an unexplained
 * em dash.
 */
export function ResourceNotice({
  state,
  onRefresh,
  className,
}: {
  state: ResourceState;
  onRefresh?: () => void;
  className?: string;
}) {
  if (state.status === "editable") return null;

  if (state.status === "stale") {
    const versions =
      state.expected !== null && state.current !== null
        ? ` You have version ${state.expected}; the current version is ${state.current}.`
        : "";
    return (
      <div
        role="status"
        className={cn(
          "flex flex-wrap items-center justify-between gap-3 rounded-[12px] border border-warning bg-surface-sunken px-4 py-3 text-sm text-foreground",
          className,
        )}
      >
        <span>Someone else saved this first.{versions} Reload to see their changes, then reapply yours.</span>
        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            className="rounded-[12px] border border-border-strong px-3 py-1.5 text-sm font-medium text-foreground hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised"
          >
            Reload
          </button>
        )}
      </div>
    );
  }

  return (
    <div
      role="status"
      className={cn(
        "rounded-[12px] border border-border-strong bg-surface-sunken px-4 py-3 text-sm text-foreground",
        className,
      )}
    >
      This is locked and cannot be changed. {state.reason}
    </div>
  );
}
