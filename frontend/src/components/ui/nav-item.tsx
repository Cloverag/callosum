import * as React from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";

export interface NavItemProps {
  href: string;
  label: string;
  /** A lucide icon element, e.g. <CalendarDays />. */
  icon: React.ReactNode;
  active?: boolean;
}

export function NavItem({ href, label, icon, active = false }: NavItemProps) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "group relative flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm transition-colors duration-150",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface-elevated",
        active
          ? "bg-accent-subtle font-semibold text-foreground"
          : "text-muted-foreground hover:bg-surface-raised hover:text-foreground"
      )}
    >
      {active && (
        <span
          className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-accent-emphasis"
          aria-hidden
        />
      )}
      <span
        className={cn(
          "flex shrink-0 [&_svg]:size-4",
          active ? "text-accent-emphasis" : "text-muted-foreground group-hover:text-foreground"
        )}
        aria-hidden
      >
        {icon}
      </span>
      <span className="truncate">{label}</span>
    </Link>
  );
}
