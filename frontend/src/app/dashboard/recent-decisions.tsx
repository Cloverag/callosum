import Link from "next/link";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  DECISION_STATUS_LABEL,
  DECISION_STATUS_TONE,
  type Decision,
} from "@/lib/decisions";

/**
 * Governed board decisions, each sourced to the meeting where it was made.
 *
 * Reads from `lib/decisions.ts`, which mirrors the shipped `meridian/decisions.py`
 * contract, rather than the invented `decisions` array that used to live in
 * `insights.ts`. That old shape carried a `"pending"` status the domain has never
 * had, and no stances at all — so the card could not show the one thing that makes
 * a decision a record rather than an assertion.
 */
export function RecentDecisions({ decisions }: { decisions: Decision[] | null }) {
  return (
    <Card className="flex h-full flex-col overflow-hidden">
      <div className="flex items-baseline justify-between gap-4 border-b border-border px-6 py-4">
        <h3 className="text-sm font-semibold text-foreground">Recent decisions</h3>
        <Link
          href="/decisions"
          className="rounded-[6px] text-xs text-accent-emphasis hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised"
        >
          All decisions →
        </Link>
      </div>

      {decisions === null ? (
        <div className="divide-y divide-border">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex items-center justify-between gap-4 px-6 py-3.5">
              <div className="h-4 w-2/3 rounded bg-surface-sunken" />
              <div className="h-5 w-16 rounded-full bg-surface-sunken" />
            </div>
          ))}
        </div>
      ) : (
        <ul className="divide-y divide-border">
          {decisions.map((d) => (
            <li key={d.id}>
              <Link
                href={`/decisions#${d.id}`}
                className="flex items-center justify-between gap-4 px-6 py-3.5 hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-foreground">{d.title}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {/* Stance count is the honest one-line summary: it says how much
                        of the board is on record, without pretending to summarise
                        their positions in a space this small. */}
                    {d.stances.length === 0
                      ? "No stances recorded"
                      : `${d.stances.length} ${d.stances.length === 1 ? "stance" : "stances"} recorded`}
                  </p>
                </div>
                <Badge tone={DECISION_STATUS_TONE[d.status]}>
                  {DECISION_STATUS_LABEL[d.status]}
                </Badge>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
