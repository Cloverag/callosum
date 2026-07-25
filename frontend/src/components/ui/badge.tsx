import * as React from "react";
import { cn } from "@/lib/utils";

export type BadgeTone = "neutral" | "accent" | "success" | "warning" | "danger" | "info" | "memory";

// Pill badges (brief: badges are full-radius). Colored badge on a neutral row is
// the only place status color appears in dense lists — meaning, not decoration.
const base =
  "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 " +
  "text-[11px] font-semibold leading-[1.35] whitespace-nowrap";

const tones: Record<BadgeTone, string> = {
  neutral: "bg-surface-sunken text-muted-foreground border-border",
  accent: "bg-accent-subtle text-accent-emphasis border-accent-border",
  success: "bg-success-subtle text-success-emphasis border-transparent",
  warning: "bg-warning-subtle text-warning-emphasis border-transparent",
  danger: "bg-danger-subtle text-danger-emphasis border-transparent",
  info: "bg-info-subtle text-info-emphasis border-accent-border",
  memory: "bg-memory-subtle text-memory-emphasis border-transparent",
};

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
}

export function Badge({ className, tone = "neutral", ...props }: BadgeProps) {
  return <span className={cn(base, tones[tone], className)} {...props} />;
}
