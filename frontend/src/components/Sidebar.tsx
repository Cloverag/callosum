"use client";

import { usePathname } from "next/navigation";
import { LayoutDashboard, CalendarDays, Users, FileText, Layers, Settings, Compass } from "lucide-react";
import { NavItem } from "./ui/nav-item";

const nav = [
  { href: "/dashboard", label: "Dashboard", icon: <LayoutDashboard /> },
  { href: "/calendar", label: "Calendar", icon: <CalendarDays /> },
  { href: "/meetings", label: "Meetings", icon: <Users /> },
  { href: "/documents", label: "Documents", icon: <FileText /> },
  { href: "/entity-conflicts", label: "Entity Conflicts", icon: <Layers /> },
  { href: "/settings", label: "Settings", icon: <Settings /> },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-full w-64 flex-col border-r border-border bg-surface-elevated">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <span className="flex size-8 items-center justify-center rounded-md bg-accent text-accent-foreground">
          <Compass className="size-5" />
        </span>
        <span className="text-lg font-medium tracking-tight text-foreground">Meridian</span>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-2">
        {nav.map((item) => (
          <NavItem
            key={item.href}
            href={item.href}
            label={item.label}
            icon={item.icon}
            active={pathname === item.href || pathname.startsWith(item.href + "/")}
          />
        ))}
      </nav>

      <div className="border-t border-border p-3">
        <button
          type="button"
          className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-left transition-colors duration-150 hover:bg-surface-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface-elevated"
        >
          <span className="flex size-8 items-center justify-center rounded-full border border-border bg-surface-raised text-xs font-medium text-foreground">
            RM
          </span>
          <span className="flex flex-col">
            <span className="text-sm font-medium text-foreground">Raj Malhotra</span>
            <span className="text-xs text-muted-foreground">Board Member</span>
          </span>
        </button>
      </div>
    </aside>
  );
}
