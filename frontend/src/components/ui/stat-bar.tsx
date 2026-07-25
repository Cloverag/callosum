import { cn } from "@/lib/utils";

export type StatSegment = {
  label: string;
  value: number;
  /** A background token utility, e.g. "bg-info" / "bg-success". */
  color: string;
};

/**
 * A single thin proportional bar with a compact legend — a distribution at a
 * glance (e.g. meetings by status). Zero-value segments are dropped, not shown.
 */
export function StatBar({
  segments,
  className,
  ariaLabel,
}: {
  segments: StatSegment[];
  className?: string;
  ariaLabel?: string;
}) {
  const shown = segments.filter((s) => s.value > 0);
  const total = shown.reduce((sum, s) => sum + s.value, 0);

  if (total === 0) {
    return <p className={cn("text-xs text-subtle-foreground", className)}>No data yet.</p>;
  }

  return (
    <div className={className}>
      <div
        className="flex h-2 w-full overflow-hidden rounded-full bg-surface-sunken"
        role="img"
        aria-label={ariaLabel ?? shown.map((s) => `${s.label}: ${s.value}`).join(", ")}
      >
        {shown.map((s) => (
          <div key={s.label} className={cn("h-full", s.color)} style={{ width: `${(s.value / total) * 100}%` }} />
        ))}
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
        {shown.map((s) => (
          <li key={s.label} className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span className={cn("size-1.5 rounded-full", s.color)} aria-hidden />
            <span>{s.label}</span>
            <span className="tabular-nums text-foreground">{s.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
