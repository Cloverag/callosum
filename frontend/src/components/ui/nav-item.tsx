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
        "group flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm transition-colors duration-150",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface-elevated",
        active
          ? "bg-accent-subtle font-medium text-foreground"
          : "text-muted-foreground hover:bg-surface-raised hover:text-foreground"
      )}
    >
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
