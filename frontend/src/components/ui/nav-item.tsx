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
        "group flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium",
        "transition-colors duration-150",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface-elevated",
        active
          ? "bg-accent-subtle text-foreground"
          : "text-muted-foreground hover:bg-surface-elevated hover:text-foreground"
      )}
    >
      <span className={cn("flex [&_svg]:size-5", active ? "text-accent-emphasis" : "text-current")} aria-hidden>
        {icon}
      </span>
      {label}
    </Link>
  );
}
