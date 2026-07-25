"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  /** Optional leading icon (e.g. a lucide <Search />). Sized and positioned automatically. */
  icon?: React.ReactNode;
  error?: boolean;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, icon, error = false, "aria-invalid": ariaInvalid, ...props }, ref) => {
    const field = (
      <input
        ref={ref}
        aria-invalid={error || ariaInvalid || undefined}
        className={cn(
          "h-10 w-full rounded-[12px] border bg-surface-raised text-sm text-foreground",
          "placeholder:text-muted-foreground transition-colors duration-150",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus/40",
          "disabled:pointer-events-none disabled:opacity-50",
          icon ? "pl-9 pr-3" : "px-3.5",
          error
            ? "border-danger focus-visible:border-danger focus-visible:ring-danger/40"
            : "border-border focus-visible:border-accent",
          className
        )}
        {...props}
      />
    );

    if (!icon) return field;

    return (
      <div className="relative flex items-center">
        <span className="pointer-events-none absolute left-3 flex text-muted-foreground [&_svg]:size-4" aria-hidden>
          {icon}
        </span>
        {field}
      </div>
    );
  }
);
Input.displayName = "Input";
