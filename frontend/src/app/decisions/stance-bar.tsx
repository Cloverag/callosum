import { cn } from "@/lib/utils";
import {
  STANCE_LABEL,
  STANCE_ORDER,
  type Decision,
  type Stance,
  stanceBreakdown,
} from "@/lib/decisions";

/**
 * Status-hued fills, not a sequential palette.
 *
 * DESIGN.md's dataviz rules require emphasis over rainbow, but stance is the one
 * case where the categories carry inherent polarity — assent and dissent are not
 * arbitrary buckets, and the existing status semantics (green success, red
 * critical, amber attention) already mean the right things. Violet is deliberately
 * absent: it is reserved for institutional memory, and a board's voting position
 * is operational data, not a memory metric.
 */
const STANCE_FILL: Record<Stance, string> = {
  APPROVED: "bg-accent",
  SUPPORTED: "bg-success",
  REQUESTED: "bg-warning",
  OPPOSED: "bg-danger",
};

/**
 * How a board actually landed on a decision, as one proportional bar.
 *
 * A bar rather than a donut: the question a reader has is "was this close?", which
 * is a length comparison, and length is read more accurately than angle. Segments
 * follow STANCE_ORDER so the spectrum runs assent → dissent left to right and the
 * shape is comparable between decisions at a glance.
 */
export function StanceBar({ decision, className }: { decision: Decision; className?: string }) {
  const rows = stanceBreakdown(decision);
  const total = rows.reduce((n, r) => n + r.count, 0);

  if (total === 0) {
    return (
      <p className={cn("text-xs text-subtle-foreground", className)}>
        No stances recorded.
      </p>
    );
  }

  // The bar alone is a picture; the label list underneath is what a screen reader
  // and a colour-blind reader actually consume, so it is not decoration.
  const summary = rows.map((r) => `${r.count} ${STANCE_LABEL[r.stance]}`).join(", ");

  return (
    <div className={className}>
      <div
        className="flex h-2 w-full overflow-hidden rounded-full bg-surface-sunken"
        role="img"
        aria-label={`Stances: ${summary}`}
      >
        {rows.map((r) => (
          <div
            key={r.stance}
            className={cn(STANCE_FILL[r.stance], "h-full")}
            style={{ width: `${(r.count / total) * 100}%` }}
          />
        ))}
      </div>

      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
        {rows.map((r) => (
          <li key={r.stance} className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span className={cn("size-1.5 rounded-full", STANCE_FILL[r.stance])} aria-hidden />
            {STANCE_LABEL[r.stance]}
            <span className="tabular-nums text-foreground">{r.count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The stance spectrum as a legend, for the filter rail. */
export function StanceLegend() {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1">
      {STANCE_ORDER.map((s) => (
        <li key={s} className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className={cn("size-1.5 rounded-full", STANCE_FILL[s])} aria-hidden />
          {STANCE_LABEL[s]}
        </li>
      ))}
    </ul>
  );
}
