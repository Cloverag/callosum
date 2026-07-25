import { BadgeCheck } from "lucide-react";
import { Card } from "@/components/ui/card";
import type { ApprovedFact } from "@/lib/insights";

/**
 * Meridian's signature panel: not a count, but the evidence behind the memory.
 * Each approved fact shows its verbatim source quote and where it was located —
 * the product stores evidence, not AI summaries.
 */
export function ApprovedFacts({ facts }: { facts: ApprovedFact[] | null }) {
  return (
    <Card className="flex h-full flex-col overflow-hidden">
      <div className="border-b border-border px-6 py-4">
        <h3 className="text-sm font-semibold text-foreground">Recent approved facts</h3>
        <p className="mt-0.5 text-xs text-muted-foreground">Evidence, not summaries — each with its source quote.</p>
      </div>

      {facts === null ? (
        <div className="divide-y divide-border">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="space-y-2 px-6 py-4">
              <div className="h-3.5 w-3/4 rounded bg-surface-sunken" />
              <div className="h-12 w-full rounded-md bg-surface-sunken" />
              <div className="h-3 w-1/3 rounded bg-surface-sunken" />
            </div>
          ))}
        </div>
      ) : (
        <ul className="divide-y divide-border">
          {facts.map((f) => (
            <li key={f.id} className="px-6 py-4">
              <p className="text-sm font-medium text-foreground">{f.statement}</p>
              <blockquote className="mt-2 rounded-md bg-surface-sunken px-3 py-2 text-xs leading-relaxed text-muted-foreground">
                <span aria-hidden className="mr-0.5 text-subtle-foreground">“</span>
                {f.quote}
                <span aria-hidden className="ml-0.5 text-subtle-foreground">”</span>
              </blockquote>
              <div className="mt-2 flex items-center gap-2 text-xs">
                <button
                  type="button"
                  className="truncate font-medium text-accent-emphasis underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised rounded-sm"
                >
                  {f.source}
                </button>
                <span className="text-border-strong" aria-hidden>·</span>
                <span className="inline-flex items-center gap-1 font-medium text-success-emphasis">
                  <BadgeCheck className="size-3.5" aria-hidden />
                  Verified
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
