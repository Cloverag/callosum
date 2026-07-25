"use client";

import { AreaChart, Area } from "@/components/charts/area-chart";
import { Grid } from "@/components/charts/grid";
import { XAxis } from "@/components/charts/x-axis";
import { ChartTooltip } from "@/components/charts/tooltip";
import { Card } from "@/components/ui/card";
import type { MemoryGrowthPoint } from "@/lib/insights";

/**
 * Institutional memory accumulating over time — the one dashboard surface where
 * a real chart earns its place. The Gauge answers "how much is verified right
 * now"; a sparkline answers "roughly which way"; neither can answer "how did we
 * get here, and when did it slow down". This can, and it stays hoverable so a
 * board member can read the actual week.
 *
 * FORM: emphasis, not two-series categorical. Verified edges are the point and
 * carry the memory violet as a filled area; entities are context and recede to
 * the neutral scale as a bare line. Two steps of one violet were tried first and
 * measured at ΔE 11.7 for normal vision — below the 15 floor, i.e. genuinely
 * hard to tell apart even with full colour vision. Violet vs slate measures
 * 21.9, and the area-vs-line contrast means identity never rests on hue alone.
 *
 * This also keeps the colour doctrine intact: violet stays Institutional Memory,
 * blue stays ACTION, and no third hue is invented to seat a second series.
 */
export function MemoryGrowth({ growth }: { growth: MemoryGrowthPoint[] | null }) {
  const ready = growth !== null && growth.length > 0;

  // The chart's x-scale is time-based, so ISO strings from the API become Dates
  // here rather than in the mock — the mock stays JSON-shaped for the P3 swap.
  const data = (growth ?? []).map((p) => ({
    date: new Date(p.date),
    edges: p.edges,
    entities: p.entities,
  }));

  const latest = ready ? growth[growth.length - 1] : null;
  const first = ready ? growth[0] : null;
  const addedEdges = latest && first ? latest.edges - first.edges : 0;

  return (
    <Card className="overflow-hidden">
      <div className="flex items-baseline justify-between gap-4 border-b border-border px-6 py-4">
        <h3 className="text-sm font-semibold text-foreground">Memory growth</h3>
        {latest && (
          <span className="text-xs text-muted-foreground">
            <span className="tabular-nums text-foreground">
              +{addedEdges.toLocaleString()}
            </span>{" "}
            verified edges in 8 weeks
          </span>
        )}
      </div>

      <div className="px-4 pb-4 pt-5">
        <AreaChart
          data={data}
          xDataKey="date"
          aspectRatio="5 / 2"
          status={ready ? "ready" : "loading"}
          loadingLabel="Reading the graph…"
          margin={{ top: 8, right: 12, bottom: 24, left: 12 }}
        >
          <Grid />
          {/* Context first, so the emphasised series paints over it. A bare
              2px line with no fill — nothing to occlude the area beneath. */}
          <Area
            dataKey="entities"
            fill="var(--subtle-foreground)"
            stroke="var(--subtle-foreground)"
            fillOpacity={0}
            gradientToOpacity={0}
            strokeWidth={2}
            showHighlight={false}
          />
          {/* The point: verified edges, in memory violet. */}
          <Area
            dataKey="edges"
            fill="var(--memory)"
            stroke="var(--memory)"
            fillOpacity={0.18}
            strokeWidth={2}
          />
          <XAxis />
          <ChartTooltip />
        </AreaChart>

        {/* Legend — always present at two series, and it doubles as the direct
            label by carrying each series' current value. Identity therefore
            never rests on colour: there is a name, a value, and a mark shape
            (filled swatch = area, rule = line) behind every series.
            The text itself stays in ink tokens; only the swatch is coloured. */}
        <div className="mt-2 flex items-center gap-6 px-2 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-2">
            <span
              className="h-2 w-3 rounded-[2px]"
              style={{ background: "var(--memory)" }}
              aria-hidden
            />
            Verified edges
            {latest && (
              <span className="tabular-nums text-foreground">
                {latest.edges.toLocaleString()}
              </span>
            )}
          </span>
          <span className="inline-flex items-center gap-2">
            <span
              className="h-0.5 w-3 rounded-full"
              style={{ background: "var(--subtle-foreground)" }}
              aria-hidden
            />
            Entities
            {latest && (
              <span className="tabular-nums text-foreground">
                {latest.entities.toLocaleString()}
              </span>
            )}
          </span>
        </div>

        {/* The contrast WARN on the de-emphasis grey obliges a non-visual route
            to the numbers; the tooltip is hover-only, so the table is it. */}
        {growth && growth.length > 0 && (
          <details className="mt-3 px-2">
            <summary className="cursor-pointer text-xs text-muted-foreground underline decoration-dotted underline-offset-4 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised">
              View as table
            </summary>
            <table className="mt-2 w-full text-xs">
              <caption className="sr-only">
                Verified edges and entities in institutional memory, by week
              </caption>
              <thead>
                <tr className="text-left text-subtle-foreground">
                  <th scope="col" className="py-1 font-medium">Week</th>
                  <th scope="col" className="py-1 text-right font-medium">Verified edges</th>
                  <th scope="col" className="py-1 text-right font-medium">Entities</th>
                </tr>
              </thead>
              <tbody className="text-muted-foreground">
                {growth.map((p) => (
                  <tr key={p.date} className="border-t border-border">
                    <td className="py-1">
                      {new Date(p.date).toLocaleDateString("en-GB", {
                        day: "numeric",
                        month: "short",
                        timeZone: "UTC",
                      })}
                    </td>
                    <td className="py-1 text-right tabular-nums text-foreground">
                      {p.edges.toLocaleString()}
                    </td>
                    <td className="py-1 text-right tabular-nums">
                      {p.entities.toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        )}
      </div>
    </Card>
  );
}
