import * as React from "react";
import { cn } from "@/lib/utils";

export interface PageHeaderProps extends React.HTMLAttributes<HTMLDivElement> {
  title: string;
  description?: string;
  /** Optional leading icon (a lucide icon element). */
  icon?: React.ReactNode;
  /** Right-aligned actions (buttons, filters). */
  actions?: React.ReactNode;
}

export function PageHeader({ title, description, icon, actions, className, ...props }: PageHeaderProps) {
  return (
    <div
      className={cn("flex items-start justify-between gap-4 border-b border-border pb-4", className)}
      {...props}
    >
      <div className="flex items-start gap-3">
        {icon && (
          <span
            className="mt-0.5 flex rounded-md border border-border bg-surface-elevated p-2 text-accent-emphasis [&_svg]:size-5"
            aria-hidden
          >
            {icon}
          </span>
        )}
        <div className="min-w-0">
          <h1 className="text-2xl font-light tracking-tight text-foreground text-balance">{title}</h1>
          {description && (
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground text-pretty">{description}</p>
          )}
        </div>
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}
