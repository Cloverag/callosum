"use client";

import * as React from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md";

const base =
  "inline-flex items-center justify-center gap-2 rounded-[12px] font-medium whitespace-nowrap select-none " +
  "transition-[color,background-color,border-color,box-shadow] duration-150 ease-out " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface " +
  "disabled:pointer-events-none disabled:opacity-50";

const variants: Record<ButtonVariant, string> = {
  // Primary is the ONE dominant action per surface — solid blue.
  primary: "bg-accent text-accent-foreground shadow-card hover:bg-accent-hover active:translate-y-px",
  // Secondary — white with a gray border (brief: "Secondary: White + gray border").
  secondary:
    "bg-surface-raised text-foreground border border-border shadow-card hover:border-border-strong hover:bg-surface-alt",
  ghost: "bg-transparent text-muted-foreground hover:text-foreground hover:bg-surface-sunken",
  danger: "bg-danger text-danger-foreground shadow-card hover:bg-danger-emphasis active:translate-y-px",
};

const sizes: Record<ButtonSize, string> = {
  sm: "h-8 px-3.5 text-[13px]",
  md: "h-10 px-5 text-sm",
};

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", loading = false, disabled, children, ...props }, ref) => (
    <button
      ref={ref}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(base, variants[variant], sizes[size], className)}
      {...props}
    >
      {loading && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  )
);
Button.displayName = "Button";
