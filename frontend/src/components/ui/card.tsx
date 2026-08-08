import * as React from "react";
import { cn } from "@/lib/utils";

type CardVariant = "default" | "elevated" | "glass";

// Cards are sheets on a desk: white surface, 1px hairline, 16px radius, a very
// subtle shadow. `elevated` lifts a little more (the meeting hero); `glass` is
// reserved for true overlays. See DESIGN.md — Cards / Elevation.
const surfaces: Record<CardVariant, string> = {
  default: "bg-surface-raised border border-border shadow-card",
  elevated: "bg-surface-raised border border-border shadow-raised",
  glass: "surface-glass", // structural glass utility — overlays only
};

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: CardVariant;
}

/**
 * `Card` is the whole component. It shipped with the usual
 * Header/Title/Description/Content/Footer set, and across 79 call sites not one
 * of them was ever used — every surface composes its own header row, because
 * the headers here differ too much (a badge and a count, a tooltip trigger, a
 * live value) for one slot to have described them. Removed rather than left as
 * an API nobody chose, and `CardTitle` was the only `h3` the design system
 * emitted, so it was also a heading level waiting to be used by mistake.
 */
export function Card({ className, variant = "default", ...props }: CardProps) {
  return <div className={cn("rounded-[16px]", surfaces[variant], className)} {...props} />;
}
