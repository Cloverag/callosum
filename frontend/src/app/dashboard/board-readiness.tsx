import { Card } from "@/components/ui/card";
import type { BoardReadiness as BoardReadinessData } from "@/lib/insights";

// Each track carries its own status hue — green/amber/blue/red communicate how
// close that part of the pack is, not decoration. Fill + track are token-driven.
const TRACKS: { key: keyof BoardReadinessData; label: string; fill: string; text: string }[] = [
  { key: "agenda", label: "Agenda", fill: "bg-success", text: "text-success-emphasis" },
  { key: "metrics", label: "Metrics", fill: "bg-warning", text: "text-warning-emphasis" },
  { key: "documents", label: "Documents", fill: "bg-accent", text: "text-accent-emphasis" },
  { key: "approvals", label: "Approvals", fill: "bg-danger", text: "text-danger-emphasis" },
];

export function BoardReadiness({ readiness }: { readiness: BoardReadinessData | null }) {
  const overall =
    readiness === null
      ? null
      : Math.round((readiness.agenda + readiness.metrics + readiness.documents + readiness.approvals) / 4);

  return (
    <Card className="p-6">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-foreground">Board readiness</h3>
        {overall !== null && (
          <span className="text-sm font-semibold tabular-nums text-accent-emphasis">{overall}% ready</span>
        )}
      </div>

      <div className="mt-4 grid gap-x-8 gap-y-4 sm:grid-cols-2">
        {TRACKS.map((t) => {
          const value = readiness?.[t.key] ?? 0;
          return (
            <div key={t.key}>
              <div className="flex items-center justify-between text-[13px]">
                <span className="font-medium text-foreground">{t.label}</span>
                <span className={`font-semibold tabular-nums ${t.text}`}>
                  {readiness === null ? "—" : `${value}%`}
                </span>
              </div>
              <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-surface-sunken">
                <div
                  className={`h-full rounded-full ${t.fill} transition-[width] duration-700 ease-out`}
                  style={{ width: `${value}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
