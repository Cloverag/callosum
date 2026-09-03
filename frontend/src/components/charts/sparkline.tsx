"use client";

import type React from "react";
import { ResponsiveContainer, LineChart, Line } from "recharts";

/**
 * Ported from Monocharts' `MonoRoundedSparklineChart`. See `area-chart.tsx`
 * for the shared rationale.
 *
 * The only one of the four with no tooltip and no `theme`/`isDark` branch
 * upstream either — it was already the smallest surface, and it's the only
 * upstream file of the four that never imported the dither tooltip. Upstream
 * rendered three named rows (CPU/GPU/fan) from its own const; that shape —
 * a label plus a value plus a series, three of them — belongs to the caller
 * composing three `Sparkline`s with their own labels, not to this component
 * inventing rows. `data` here is one series: `number[]`, nothing else.
 */

export function Sparkline({ data, ariaLabel }: { data: number[]; ariaLabel: string }): React.JSX.Element {
  if (data.length === 0) {
    return (
      <div role="img" aria-label={ariaLabel} style={{ color: "var(--muted-foreground)", fontSize: "13px" }}>
        Nothing to show.
      </div>
    );
  }

  const points = data.map((value, index) => ({ index, value }));

  return (
    <div role="img" aria-label={ariaLabel} style={{ width: "100%", height: "100%" }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points}>
          <Line
            type="monotone"
            dataKey="value"
            stroke="var(--chart-1)"
            strokeWidth={2}
            strokeLinecap="round"
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
