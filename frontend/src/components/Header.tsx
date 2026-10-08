"use client";

import { useState } from "react";
import { Menu } from "lucide-react";
import { Button } from "./ui/button";
import { useSession } from "./session-gate";
import { ThemeToggle } from "./theme";

/**
 * The application header: where you are, who you are, and the way out.
 *
 * ---------------------------------------------------------------------------
 * WHAT WAS REMOVED, AND WHY
 * ---------------------------------------------------------------------------
 * This header used to carry a notification bell and a search box. Neither did
 * anything.
 *
 * The bell had no handler and rendered a permanent blue dot — a standing claim that
 * something was waiting for the reader. Nothing could be: **CP9 (notification) is
 * deferred to P8 (#62)**, and the product contains no dispatcher, adapter, scheduler or
 * trigger of any kind. An unread indicator for a subsystem that does not exist is the
 * same class of defect as a count that was never measured.
 *
 * The search input had no `value`, no `onChange` and no submit path, but bound `⌘K` to
 * focus itself — so it felt wired, invited typing, and could never answer. Search is
 * not in this phase; the honest treatment is absence, not a disabled control, which
 * would still promise the feature is coming.
 *
 * ---------------------------------------------------------------------------
 * WHAT REPLACED THEM
 * ---------------------------------------------------------------------------
 * The signed-in principal, taken from `/auth/context` through `useSession()` — the
 * single fetch the gate already makes. Name, role and clearance are read from the
 * session; none of the three is hard-coded, and this component does not fetch for
 * itself, because a header naming one principal above another's data is worse than a
 * header naming nobody.
 *
 * **Clearance is shown deliberately.** It is the value that decides what every surface
 * below returns — which documents load, which pack items survive filtering, which
 * graph nodes are withheld. Printing it makes an authorization difference legible from
 * a screenshot rather than requiring narration.
 *
 * **The breadcrumb names no workspace.** It used to read "Acme Corp / Series B" — the
 * fictional company the seeded corpus is written about — on the reasoning that
 * `/auth/context` returns a `workspace_id` and no name, so a real one could not be
 * resolved. That reasoning justifies omitting the name; it does not justify printing a
 * different one. The workspace this session is actually in is called "Default
 * Workspace", so the header asserted a fact that was both unmeasured and wrong, in the
 * one product whose thesis is that it will not do that. "Series B" was worse: nothing
 * in the domain models a funding stage at all.
 *
 * The id is shown instead, because it is the only workspace identity the session
 * genuinely holds. When the API grows a name, this is the one place to change.
 */
export default function Header({ onMenuClick }: { onMenuClick?: () => void }) {
  const session = useSession();
  const [signingOut, setSigningOut] = useState(false);

  async function signOut() {
    if (!session) return;
    setSigningOut(true);
    try {
      await session.signOut();
    } finally {
      setSigningOut(false);
    }
  }

  return (
    <header className="surface-glass-chrome flex h-16 shrink-0 items-center justify-between gap-3 border-b border-border px-4 lg:gap-4 lg:px-6">
      <div className="flex min-w-0 items-center gap-2.5">
        {/*
          The drawer trigger, mobile only. `lg:hidden` because at `lg` and up the
          static sidebar is always present and there is nothing to open. Base UI's
          Dialog restores focus here on close.
        */}
        <button
          type="button"
          onClick={onMenuClick}
          aria-label="Open navigation"
          className="-ml-1 grid size-9 shrink-0 place-items-center rounded-[10px] text-muted-foreground transition-colors duration-(--duration-hover) hover:bg-surface-sunken hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus lg:hidden"
        >
          <Menu className="size-5" aria-hidden />
        </button>

        <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-2.5 text-sm">
          <span className="shrink-0 text-muted-foreground">Workspace</span>
          <span className="shrink-0 text-border-strong" aria-hidden>/</span>
          <span
            className="truncate font-mono text-[13px] font-medium text-foreground"
            title={session?.context.workspace_id ?? undefined}
          >
            {session ? session.context.workspace_id.slice(0, 8) : "—"}
          </span>
        </nav>
      </div>

      {session && (
        <div className="flex shrink-0 items-center gap-2 lg:gap-4">
          <ThemeToggle />
          {/*
            The name/role/clearance block is the first thing to fold away on a
            narrow screen — it is context, not a control. Below `sm` only the
            theme toggle and the way out survive. Clearance still reaches the
            reader on the Settings page, which prints it in full.
          */}
          <div className="hidden text-right leading-tight sm:block">
            <p className="text-sm font-medium text-foreground">{session.context.name}</p>
            <p className="text-xs text-muted-foreground">
              {session.context.role}
              <span className="mx-1.5 text-border-strong" aria-hidden>·</span>
              {/*
                Spelled out rather than shown as a bare number. "Clearance 4" is a fact
                about this session; a lone "4" beside a job title reads as a rank.
              */}
              Clearance {session.context.clearance}
            </p>
          </div>
          <Button variant="secondary" size="sm" onClick={signOut} loading={signingOut}>
            Sign out
          </Button>
        </div>
      )}
    </header>
  );
}
