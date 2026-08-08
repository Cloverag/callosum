import { Card } from "@/components/ui/card";
import type { BoardReadiness as BoardReadinessData } from "@/lib/insights";

/**
 * One hue, because this is magnitude and not identity.
 *
 * Each track used to carry a fixed status colour — Agenda green, Metrics amber,
 * Documents blue, Approvals red. The hue was bound to the ROW, never to the
 * VALUE, so Agenda rendered green at 20% and Approvals rendered red at 100%:
 * the colour actively contradicted the number beside it. It also spent four
 * hues on a dashboard whose doctrine is 95% neutral, and used blue — reserved
 * for action — as a data fill.
 *
 * All four tracks measure the same thing on the same 0–100 scale, so they share
 * one neutral ink fill and the percentage carries the reading. This is the form
 * `graph-quality.tsx` already uses, for the same stated reason.
 */
const TRACKS: { key: keyof BoardReadinessData; label: string }[] = [
  { key: "agenda", label: "Agenda" },
  { key: "metrics", label: "Metrics" },
  { key: "documents", label: "Documents" },
  { key: "approvals", label: "Approvals" },
];

export function BoardReadiness({ readiness }: { readiness: BoardReadinessData | null }) {
  const overall =
    readiness === null
      ? null
      : Math.round((readiness.agenda + readiness.metrics + readiness.documents + readiness.approvals) / 4);

  return (
    <Card className="p-6">
      <div className="flex items-center justify-between">
        {/* h2, not h3: this card sits in Band A alongside MeetingHero and
            NeedsYou, which both head at h2. Band B's cards are h3 because they
            nest under the "Institutional memory" h2. Three siblings at two
            levels made the outline claim a nesting the layout does not have. */}
        <h2 className="text-sm font-semibold text-foreground">Board readiness</h2>
        {/* Ink, not accent: blue means action, and a readout is not an action. */}
        {overall !== null && (
          <span className="text-sm font-semibold tabular-nums text-foreground">{overall}% ready</span>
        )}
      </div>

      <div className="mt-4 grid gap-x-8 gap-y-4 sm:grid-cols-2">
        {TRACKS.map((t) => {
          const value = readiness?.[t.key] ?? 0;
          return (
            <div key={t.key}>
              <div className="flex items-baseline justify-between text-[13px]">
                <span className="font-medium text-foreground">{t.label}</span>
                <span className="font-semibold tabular-nums text-foreground">
                  {readiness === null ? "—" : `${value}%`}
                </span>
              </div>
              <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-surface-sunken">
                <div
                  className="h-full rounded-full bg-muted-foreground transition-[width] duration-[--duration-state] ease-out"
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
