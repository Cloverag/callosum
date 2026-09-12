"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import Sidebar, { MobileNav } from "@/components/Sidebar";
import Header from "@/components/Header";
import { AssistantRail } from "@/components/AssistantRail";

/**
 * The application chrome: the static sidebar, the header, the scrolling main
 * area, and the assistant rail — plus the one piece of state the shell owns,
 * whether the mobile nav drawer is open.
 *
 * A client component only because the drawer needs `useState`. `children` is a
 * prop, not an import, so the routed page underneath stays a Server Component:
 * it arrives here already rendered and passes straight through to `<main>`.
 *
 * `layout.tsx` used to hold this JSX inline. It moved here so the drawer's
 * open/close state can be shared between the header's hamburger and the
 * `MobileNav` drawer without making the whole layout a client module.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const [navOpen, setNavOpen] = useState(false);
  const pathname = usePathname();

  // Close the drawer when the route changes. Tapping a link inside it should not
  // leave it hanging open over the page it navigated to.
  useEffect(() => {
    setNavOpen(false);
  }, [pathname]);

  // Close the drawer if the viewport grows past the static-sidebar breakpoint.
  // 1024px is Tailwind's `lg`, the same breakpoint the sidebar's `lg:flex` and
  // the drawer's `lg:hidden` use — kept in sync by hand because Tailwind v4 has
  // no JS-readable config here. Without this, a resize while the drawer is open
  // leaves Base UI's focus trap active on a `display:none` element.
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const onChange = () => {
      if (mq.matches) setNavOpen(false);
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  return (
    <div className="flex h-screen overflow-hidden bg-surface text-foreground">
      <Sidebar />
      <MobileNav open={navOpen} onOpenChange={setNavOpen} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header onMenuClick={() => setNavOpen(true)} />
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
      <AssistantRail />
    </div>
  );
}
