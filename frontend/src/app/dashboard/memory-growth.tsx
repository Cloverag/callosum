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
 * Violet throughout: this is an Institutional Memory surface, and DESIGN.md
 * reserves violet for exactly that. `chart-1` / `chart-2` are the sequential
 * memory ramp defined in shadcn-compat.css — never blue, which means ACTION.
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
          <Area
            dataKey="edges"
            fill="var(--color-chart-1)"
            stroke="var(--color-chart-1)"
            fillOpacity={0.24}
          />
          <Area
            dataKey="entities"
            fill="var(--color-chart-2)"
            stroke="var(--color-chart-2)"
            fillOpacity={0.14}
          />
          <XAxis />
          <ChartTooltip />
        </AreaChart>

        {/* Legend. Status is carried by the label, not by colour alone — the
            two violets are close by design, so colour is never the only cue. */}
        <div className="mt-2 flex items-center gap-5 px-2 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-2">
            <span
              className="size-2 rounded-full"
              style={{ background: "var(--color-chart-1)" }}
              aria-hidden
            />
            Edges
            {latest && (
              <span className="tabular-nums text-foreground">
                {latest.edges.toLocaleString()}
              </span>
            )}
          </span>
          <span className="inline-flex items-center gap-2">
            <span
              className="size-2 rounded-full"
              style={{ background: "var(--color-chart-2)" }}
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
      </div>
    </Card>
  );
}
