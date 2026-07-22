"use client";

import { usePathname } from "next/navigation";
import { LayoutDashboard, CalendarDays, Users, FileText, Layers, Settings, ChevronsUpDown } from "lucide-react";
import { NavItem } from "./ui/nav-item";

const nav = [
  { href: "/dashboard", label: "Dashboard", icon: <LayoutDashboard /> },
  { href: "/calendar", label: "Calendar", icon: <CalendarDays /> },
  { href: "/meetings", label: "Meetings", icon: <Users /> },
  { href: "/documents", label: "Documents", icon: <FileText /> },
  { href: "/entity-conflicts", label: "Entity Conflicts", icon: <Layers /> },
  { href: "/settings", label: "Settings", icon: <Settings /> },
];

// A thin-stroke meridian glyph — a restrained brand mark, not a filled app-icon square.
function MeridianMark() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      className="shrink-0 text-accent-emphasis"
      aria-hidden
    >
      <circle cx="12" cy="12" r="8.5" />
      <ellipse cx="12" cy="12" rx="3.6" ry="8.5" />
      <line x1="3.5" y1="12" x2="20.5" y2="12" />
    </svg>
  );
}

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-full w-64 flex-col border-r border-border bg-surface-elevated">
      <div className="flex h-16 items-center gap-2 border-b border-border px-4">
        <MeridianMark />
        <span className="text-sm font-semibold tracking-tight text-foreground">Meridian</span>
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto px-2.5 py-3">
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

      <div className="border-t border-border p-2.5">
        <button
          type="button"
          className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left transition-colors duration-150 hover:bg-surface-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface-elevated"
        >
          <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-surface-raised text-xs font-medium text-muted-foreground ring-1 ring-inset ring-border">
            RM
          </span>
          <span className="flex min-w-0 flex-1 flex-col leading-tight">
            <span className="truncate text-sm font-medium text-foreground">Raj Malhotra</span>
            <span className="truncate text-xs text-muted-foreground">Board Member</span>
          </span>
          <ChevronsUpDown className="size-4 shrink-0 text-muted-foreground" aria-hidden />
        </button>
      </div>
    </aside>
  );
}
