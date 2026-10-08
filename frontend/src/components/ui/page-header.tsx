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
      className={cn(
        // Below `lg`: title and actions stack, and the actions row is allowed to
        // wrap — several pages (calendar especially) carry a view switcher plus
        // date nav plus a create button that is ~600px of controls and cannot
        // share a row with the title on a phone or a tablet. At `lg` and up this
        // is exactly the row it always was.
        "flex flex-col gap-4 border-b border-border pb-4",
        "lg:flex-row lg:items-start lg:justify-between",
        className,
      )}
      {...props}
    >
      <div className="flex items-start gap-3">
        {icon && (
          <span
            className="mt-0.5 flex rounded-[12px] border border-border bg-surface-raised p-2 text-muted-foreground shadow-card [&_svg]:size-5"
            aria-hidden
          >
            {icon}
          </span>
        )}
        <div className="min-w-0">
          <h1 className="text-3xl font-bold leading-tight tracking-[-0.02em] text-foreground text-balance">{title}</h1>
          {description && (
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground text-pretty">{description}</p>
          )}
        </div>
      </div>
      {actions && (
        <div className="flex flex-wrap items-center gap-2 lg:shrink-0 lg:flex-nowrap">{actions}</div>
      )}
    </div>
  );
}
