import * as React from "react";
import { cn } from "@/lib/utils";

export type BadgeTone = "neutral" | "accent" | "success" | "warning" | "danger" | "info";

const base =
  "inline-flex items-center gap-1 rounded-sm border px-2 py-0.5 " +
  "text-[10px] font-semibold uppercase tracking-[0.08em] leading-none whitespace-nowrap";

const tones: Record<BadgeTone, string> = {
  neutral: "bg-surface-sunken text-muted-foreground border-border",
  accent: "bg-accent-subtle text-accent-emphasis border-transparent",
  success: "bg-success-subtle text-success-emphasis border-transparent",
  warning: "bg-warning-subtle text-warning-emphasis border-transparent",
  danger: "bg-danger-subtle text-danger-emphasis border-transparent",
  info: "bg-info-subtle text-info-emphasis border-transparent",
};

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
}

export function Badge({ className, tone = "neutral", ...props }: BadgeProps) {
  return <span className={cn(base, tones[tone], className)} {...props} />;
}
