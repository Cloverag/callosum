"use client";

import { usePointerSheen } from "@/hooks/use-pointer-sheen";
import type { MemoryHealth } from "@/lib/insights";

/**
 * The second focal surface — elevation level 4, `rules.md` §6 (2026-08-13).
 *
 * `--focal-memory` has existed since the focal tokens shipped and nothing
 * consumed it: the ramp was declared, contrast-gated at every stop, registered
 * in `palette-contrast.test.ts` as "the institutional-memory band" — and then
 * the band it was named for stayed a 10px uppercase eyebrow. This is that band.
 *
 * It is the page's second focal surface and its last: `action` carries the
 * operational hero above, `memory` carries this, and the rule is a count. A
 * third would mean the page has no focal surface at all.
 *
 * Why a band rather than promoting the graph-health card: everything inside that
 * card — the violet gauge, the status dots, the sunken quote wells — is tuned for
 * a light ground and would have to be re-inked to sit on a deep ramp. A band
 * introduces the section without touching what the section contains, and it is
 * the section, not any one card, that the violet identity belongs to.
 */
export function InstitutionalMemoryBand({ memory }: { memory: MemoryHealth | null }) {
  const sheen = usePointerSheen<HTMLElement>();

  return (
    <section
      {...sheen}
      className="surface-focal-memory flex flex-wrap items-end justify-between gap-x-8 gap-y-4 rounded-(--radius-card) px-7 py-6"
    >
      <div className="min-w-0">
        <span className="text-[10px] font-semibold uppercase tracking-[0.1em] text-focal-foreground/70">
          Institutional memory
        </span>
        <h2 className="mt-1.5 text-xl font-medium tracking-tight text-focal-foreground">
          What the record knows, and how well it knows it
        </h2>
        <p className="mt-1.5 max-w-prose text-sm text-focal-foreground/75">
          Nothing below was written by a model. Every edge carries a source quote located
          verbatim in the document it came from.
        </p>
      </div>

      {/*
       * The headline figure. It restates the gauge beneath it deliberately, and
       * that is the whole argument for the band: the section's thesis is the
       * verified share, and the gauge is its detail. Both read the single
       * `memory.verifiedPct` field, so the two cannot disagree — a restated
       * number is only a hazard when it has a second source.
       *
       * `null` is "insights have not loaded", not "nothing measured": the band
       * holds its own skeleton rather than collapsing, for the reason the hero
       * does — a focal surface that disappears while the page loads takes the
       * page's hierarchy with it and hands it back a beat later.
       */}
      <div className="shrink-0 text-right">
        {memory === null ? (
          <div className="ml-auto h-10 w-24 rounded bg-focal-foreground/15" aria-hidden />
        ) : (
          <div className="text-4xl font-light tabular-nums leading-none text-focal-foreground">
            {memory.verifiedPct}%
          </div>
        )}
        <div className="mt-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-focal-foreground/70">
          Verified edges
        </div>
      </div>
    </section>
  );
}
