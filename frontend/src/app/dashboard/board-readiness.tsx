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

      {/*
        Nothing computes readiness yet (`insights.ts` — "percentages without a
        denominator are a mood"), so this card has no data rather than zero data.

        It used to render the tracks anyway: the value read "—" while the bar
        beside it drew at 0% width. Those say different things. The em dash is
        the honest one — not measured — and an empty track is a plausible zero,
        which is exactly the substitution §2 exists to prevent. A reader scanning
        four empty bars concludes the board is 0% ready, not that nobody measured.

        So the tracks are named without being scored: the reader learns what
        would be tracked, and is told plainly why there is no number.
      */}
      {readiness === null ? (
        <div className="mt-4">
          <p className="text-[13px] text-muted-foreground">
            Not measured. Each track needs a stated denominator before it can carry a
            percentage — agenda items with a presenter, packs published against a
            scheduled meeting, decisions moved out of <span className="font-medium">proposed</span>.
          </p>
          <ul className="mt-3 flex flex-wrap gap-1.5">
            {TRACKS.map((t) => (
              <li
                key={t.key}
                className="rounded-full border border-border bg-surface-sunken px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground"
              >
                {t.label}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="mt-4 grid gap-x-8 gap-y-4 sm:grid-cols-2">
          {TRACKS.map((t) => {
            const value = readiness[t.key];
            return (
              <div key={t.key}>
                <div className="flex items-baseline justify-between text-[13px]">
                  <span className="font-medium text-foreground">{t.label}</span>
                  <span className="font-semibold tabular-nums text-foreground">{value}%</span>
                </div>
                <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-surface-sunken">
                  <div
                    className="h-full rounded-full bg-muted-foreground transition-[width] duration-(--duration-state) ease-out"
                    style={{ width: `${value}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
