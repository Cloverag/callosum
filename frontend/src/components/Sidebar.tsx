"use client";

import { usePathname } from "next/navigation";
import { LayoutDashboard, CalendarDays, Users, FileText, Gavel, Network, GitMerge, Settings, ChevronsUpDown } from "lucide-react";
import { NavItem } from "./ui/nav-item";

const nav = [
  { href: "/dashboard", label: "Dashboard", icon: <LayoutDashboard /> },
  { href: "/calendar", label: "Calendar", icon: <CalendarDays /> },
  { href: "/meetings", label: "Meetings", icon: <Users /> },
  // Decisions sits after Meetings because that is where they come from, and
  // before Documents because a founder reaches for the decision far more often
  // than for the file it came in on.
  { href: "/decisions", label: "Decisions", icon: <Gavel /> },
  { href: "/documents", label: "Documents", icon: <FileText /> },
  { href: "/memory", label: "Institutional Memory", icon: <Network /> },
  { href: "/entity-conflicts", label: "Review queue", icon: <GitMerge /> },
  { href: "/settings", label: "Settings", icon: <Settings /> },
];

// The Meridian mark: a wireframe globe with a highlighted meridian — the line of
// reference the product is named for. Thin stroke on a solid blue tile.
function MeridianMark() {
  return (
    <span className="grid size-8 shrink-0 place-items-center rounded-[10px] bg-accent text-accent-foreground shadow-card">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <circle cx="12" cy="12" r="8.5" />
        <path d="M12 3.5c-3.2 2.4-3.2 14.6 0 17" opacity="0.6" />
        <path d="M12 3.5c3.2 2.4 3.2 14.6 0 17" />
        <line x1="3.6" y1="12" x2="20.4" y2="12" opacity="0.6" />
      </svg>
    </span>
  );
}

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-full w-[248px] shrink-0 flex-col border-r border-border bg-surface-elevated">
      <div className="flex h-16 items-center gap-2.5 px-4">
        <MeridianMark />
        <span className="text-base font-semibold tracking-tight text-foreground">Meridian</span>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 pb-3">
        <div className="px-2.5 pb-1.5 pt-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-subtle-foreground">
          Workspace
        </div>
        <div className="space-y-0.5">
          {nav.map((item) => (
            <NavItem
              key={item.href}
              href={item.href}
              label={item.label}
              icon={item.icon}
              active={pathname === item.href || pathname.startsWith(item.href + "/")}
            />
          ))}
        </div>
      </nav>

      <div className="border-t border-border p-3">
        <button
          type="button"
          className="flex w-full items-center gap-2.5 rounded-[10px] px-2 py-1.5 text-left transition-colors duration-150 hover:bg-surface-sunken focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface-elevated"
        >
          <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent-subtle text-xs font-semibold text-accent-emphasis ring-1 ring-inset ring-accent-border">
            AC
          </span>
          <span className="flex min-w-0 flex-1 flex-col leading-tight">
            <span className="truncate text-sm font-medium text-foreground">Alex Chen</span>
            <span className="truncate text-xs text-muted-foreground">Founder &amp; CEO</span>
          </span>
          <ChevronsUpDown className="size-4 shrink-0 text-subtle-foreground" aria-hidden />
        </button>
      </div>
    </aside>
  );
}
