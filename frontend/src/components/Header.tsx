"use client";

import { useEffect, useRef, useState } from "react";
import { Bell, Search } from "lucide-react";
import { Input } from "./ui/input";
import { Badge } from "./ui/badge";

export default function Header() {
  const searchRef = useRef<HTMLInputElement>(null);
  const [modKey, setModKey] = useState("⌘");

  useEffect(() => {
    // Show the platform-correct modifier (⌘ on macOS, Ctrl elsewhere).
    const isMac = /mac/i.test(navigator.platform) || /mac/i.test(navigator.userAgent);
    setModKey(isMac ? "⌘" : "Ctrl");

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <header className="surface-glass-chrome flex h-16 shrink-0 items-center justify-between gap-4 border-b border-border px-6">
      <nav aria-label="Breadcrumb" className="flex items-center gap-2.5 text-sm">
        <span className="text-muted-foreground">Workspace</span>
        <span className="text-border-strong" aria-hidden>/</span>
        <span className="font-medium text-foreground">Acme Corp</span>
        <Badge tone="neutral">Series B</Badge>
      </nav>

      <div className="flex items-center gap-2">
        <div className="relative">
          <Input
            ref={searchRef}
            icon={<Search />}
            type="search"
            placeholder="Search Meridian…"
            aria-label="Search Meridian"
            className="w-72 pr-16"
          />
          <kbd
            aria-hidden
            className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 rounded-md border border-border bg-surface-sunken px-1.5 py-0.5 font-sans text-[10px] font-medium tabular-nums text-muted-foreground"
          >
            {modKey} K
          </kbd>
        </div>
        <button
          type="button"
          aria-label="Notifications"
          className="relative flex size-9 items-center justify-center rounded-[10px] text-muted-foreground transition-colors duration-150 hover:bg-surface-sunken hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface-elevated"
        >
          <Bell className="size-5" />
          <span className="absolute right-2 top-2 size-2 rounded-full bg-accent ring-2 ring-surface-elevated" aria-hidden />
        </button>
      </div>
    </header>
  );
}
