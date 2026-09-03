"use client";

import type React from "react";
import { ResponsiveContainer, RadialBarChart, RadialBar, PolarAngleAxis } from "recharts";

/**
 * Ported from Monocharts' `MonoRoundedRadialGaugeChart`. See `area-chart.tsx`
 * for the shared rationale.
 *
 * Upstream rendered three concentric rings from its own `RADIAL_GAUGE_DATA`
 * const, each an independent value/name pair, plus a headline "90% core
 * utilization" read off the first ring. The signature this was ported to is
 * `{ value, max }` — one ring, nothing computed. `data` is one row built from
 * exactly those two numbers; there is no second or third ring to invent,
 * because upstream's other two rings were its own fixture data and rule (a)
 * is what removes that.
 *
 * No tooltip. Upstream's had one; a single-ring gauge showing `value` and
 * `max` on hover would restate what `ariaLabel` and the caller's own on-page
 * copy already say — not a case the four-prop contract asks for.
 */

export function RadialGauge({ value, max, ariaLabel }: { value: number; max: number; ariaLabel: string }): React.JSX.Element {
  if (max <= 0) {
    return (
      <div role="img" aria-label={ariaLabel} style={{ color: "var(--muted-foreground)", fontSize: "13px" }}>
        Nothing to show.
      </div>
    );
  }

  const data = [{ name: "value", val: value }];

  return (
    <div role="img" aria-label={ariaLabel} style={{ width: "100%", height: "100%" }}>
      <ResponsiveContainer width="100%" height="100%">
        <RadialBarChart
          cx="50%"
          cy="50%"
          innerRadius="70%"
          outerRadius="90%"
          barSize={10}
          data={data}
          startAngle={90}
          endAngle={-270}
        >
          {/*
            A single-row RadialBarChart otherwise derives its domain from the
            data it was given — min and max of one row are the same number —
            so the ring would render full at any value without this. It is
            invisible (`tick={false}`) purely to fix the scale.
          */}
          <PolarAngleAxis type="number" domain={[0, max]} angleAxisId={0} tick={false} />
          <RadialBar
            background={{ fill: "var(--border)" }}
            dataKey="val"
            cornerRadius={5}
            fill="var(--chart-1)"
            isAnimationActive={false}
          />
        </RadialBarChart>
      </ResponsiveContainer>
    </div>
  );
}
