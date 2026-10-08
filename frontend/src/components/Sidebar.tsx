"use client";

import { usePathname } from "next/navigation";
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import { LayoutDashboard, CalendarDays, Users, FileText, Gavel, Scale, ClipboardCheck, ClipboardList, Briefcase, ScrollText, Network, GitMerge, Settings } from "lucide-react";
import { cn } from "@/lib/utils";
import { NavItem } from "./ui/nav-item";

const nav = [
  { href: "/dashboard", label: "Dashboard", icon: <LayoutDashboard /> },
  // Directly after Dashboard: preparing the next meeting is the thing a founder
  // arrives to do, and the dashboard's hero sends them here.
  { href: "/prepare", label: "Prepare meeting", icon: <ClipboardList /> },
  { href: "/calendar", label: "Calendar", icon: <CalendarDays /> },
  { href: "/meetings", label: "Meetings", icon: <Users /> },
  // Decisions sits after Meetings because that is where they come from, and
  // before Documents because a founder reaches for the decision far more often
  // than for the file it came in on.
  { href: "/decisions", label: "Decisions", icon: <Gavel /> },
  // Decision -> Resolution -> Commitment is the FR-EXEC-02 chain: what was
  // concluded, the formal instrument recording it, and the work it produced. They
  // are three separate objects and the nav follows that order, because it is how a
  // founder traces one to the next.
  { href: "/resolutions", label: "Resolutions", icon: <Scale /> },
  { href: "/commitments", label: "Commitments", icon: <ClipboardCheck /> },
  // Board packs sit between Decisions and Documents: a pack is the bundle a
  // meeting was read into, which is a step closer to the decision than the loose
  // file is.
  { href: "/packs", label: "Board packs", icon: <Briefcase /> },
  // Minutes follow packs: the pre-read, then the record of what came of it.
  { href: "/minutes", label: "Minutes", icon: <ScrollText /> },
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

/**
 * The logo lockup and the nav list — the whole content of the rail, minus the
 * `<aside>` frame. Shared verbatim between the static desktop rail and the
 * mobile drawer so the two cannot drift.
 *
 * `onNavigate` fires on any click inside the list (a `<Link>` activation, by
 * mouse or keyboard, bubbles a click). The drawer passes it to close itself —
 * the route-change effect in `app-shell.tsx` covers navigation to a NEW route,
 * but tapping the link for the route you are already on changes nothing and
 * would otherwise leave the drawer sitting open over the page.
 */
function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <>
      <div className="flex h-16 items-center gap-2.5 px-4">
        <MeridianMark />
        <span className="text-base font-semibold tracking-tight text-foreground">Meridian</span>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 pb-3" onClick={onNavigate}>
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

      {/*
        The account block that sat here is gone. It read "Alex Chen · Founder & CEO"
        with an "AC" avatar — hard-coded, and nobody's actual session. Once the header
        began showing the real principal from `/auth/context`, the contradiction was
        visible on one screen: the sidebar named one person while the header named
        whoever had signed in.

        It was also a `<button>` with no handler, carrying a chevron that implied an
        account switcher the product does not have.

        Not replaced with the real identity, because the header already shows it.
        Naming the signed-in principal twice invites the two to disagree again the
        moment one of them is changed.
      */}
    </>
  );
}

/**
 * The static rail. Unchanged at `lg` and up — same `w-[248px]` column, same
 * border, same surface. Below `lg` it is `hidden` and `MobileNav` takes over;
 * this is the only breakpoint in the shell and the desktop layout is byte-for-
 * byte what it was.
 */
export default function Sidebar() {
  return (
    <aside className="hidden h-full w-[248px] shrink-0 flex-col border-r border-border bg-surface-elevated lg:flex">
      <SidebarNav />
    </aside>
  );
}

/**
 * The same rail as an off-canvas drawer, below `lg` only. Built on Base UI's
 * Dialog — the primitive traps focus, sets `role="dialog"` + `aria-modal`,
 * closes on Escape and on a backdrop click, makes the rest of the page inert,
 * and restores focus to the trigger (the header hamburger) on close. The only
 * thing added here is the left-edge slide, via `data-starting-style` /
 * `data-ending-style` and the motion tokens — same idiom as
 * `components/ui/dialog.tsx`.
 */
export function MobileNav({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Backdrop
          className={cn(
            "fixed inset-0 z-50 bg-black/40 backdrop-blur-sm lg:hidden",
            "transition-opacity duration-(--duration-state) ease-(--ease-out-quart)",
            "data-starting-style:opacity-0 data-ending-style:opacity-0",
          )}
        />
        <DialogPrimitive.Popup
          // Base UI sets `role="dialog"` and makes the rest of the page inert
          // while open (`modal`, on by default). `aria-modal` is stated on top of
          // that — redundant with inert, but it is the attribute a reviewer asked
          // for by name and it costs a hint, not a behaviour.
          aria-modal="true"
          className={cn(
            "fixed inset-y-0 left-0 z-50 flex w-[248px] flex-col border-r border-border bg-surface-elevated outline-none lg:hidden",
            "transition-transform duration-(--duration-state) ease-(--ease-out-quart)",
            "data-starting-style:-translate-x-full data-ending-style:-translate-x-full",
          )}
        >
          <DialogPrimitive.Title className="sr-only">Workspace navigation</DialogPrimitive.Title>
          <SidebarNav onNavigate={() => onOpenChange(false)} />
        </DialogPrimitive.Popup>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
