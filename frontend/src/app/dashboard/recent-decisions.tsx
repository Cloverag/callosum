import { Card } from "@/components/ui/card";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import type { Decision, DecisionStatus } from "@/lib/insights";

const STATUS_TONE: Record<DecisionStatus, BadgeTone> = {
  approved: "success",
  pending: "warning",
  proposed: "info",
};

const STATUS_LABEL: Record<DecisionStatus, string> = {
  approved: "Approved",
  pending: "Pending",
  proposed: "Proposed",
};

/** Governed board decisions, each sourced to the meeting where it was made. */
export function RecentDecisions({ decisions }: { decisions: Decision[] | null }) {
  return (
    <Card className="flex h-full flex-col overflow-hidden">
      <div className="border-b border-border px-5 py-3">
        <h3 className="text-sm font-medium text-foreground">Recent decisions</h3>
      </div>

      {decisions === null ? (
        <div className="divide-y divide-border">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex items-center justify-between gap-4 px-5 py-3.5">
              <div className="h-4 w-2/3 rounded bg-surface-raised" />
              <div className="h-5 w-16 rounded-full bg-surface-raised" />
            </div>
          ))}
        </div>
      ) : (
        <ul className="divide-y divide-border">
          {decisions.map((d) => (
            <li key={d.id} className="flex items-center justify-between gap-4 px-5 py-3.5">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-foreground">{d.title}</p>
                <p className="truncate text-xs text-muted-foreground">{d.meeting}</p>
              </div>
              <Badge tone={STATUS_TONE[d.status]}>{STATUS_LABEL[d.status]}</Badge>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
