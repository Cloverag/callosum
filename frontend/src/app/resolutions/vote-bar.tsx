"use client";

import { cn } from "@/lib/utils";
import { COUNTED_VOTES, VOTE_LABEL, VOTE_ORDER, tally, type Resolution, type Vote } from "@/lib/resolutions";

/**
 * How the board split, as a proportional bar plus a legend.
 *
 * The bar is drawn over **counted votes only** (`for` + `against`). Abstentions and
 * recusals appear in the legend but not the bar, because giving them width would
 * read as a share of the outcome — and neither weighs on it. A recusal in
 * particular is a declared conflict, not a soft "against".
 */

const VOTE_FILL: Record<Vote, string> = {
  for: "bg-success",
  against: "bg-danger",
  abstain: "bg-subtle-foreground",
  recused: "bg-warning",
};

export function VoteBar({ resolution, className }: { resolution: Resolution; className?: string }) {
  const t = tally(resolution);

  if (resolution.votes.length === 0) {
    return (
      <p className={cn("text-xs text-subtle-foreground", className)}>
        No votes recorded.
      </p>
    );
  }

  return (
    <div className={className}>
      {t.counted > 0 && (
        <div
          className="flex h-2 overflow-hidden rounded-full bg-surface-sunken"
          role="img"
          aria-label={`${t.for} for, ${t.against} against`}
        >
          {COUNTED_VOTES.map((v) => {
            const n = t[v as "for" | "against"];
            if (n === 0) return null;
            return (
              <div
                key={v}
                className={VOTE_FILL[v]}
                style={{ width: `${(n / t.counted) * 100}%` }}
              />
            );
          })}
        </div>
      )}

      <ul className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
        {VOTE_ORDER.map((v) => {
          const n = t[v];
          if (n === 0) return null;
          return (
            <li key={v} className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className={cn("size-1.5 rounded-full", VOTE_FILL[v])} aria-hidden />
              {VOTE_LABEL[v]}
              <span className="tabular-nums text-foreground">{n}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
