"use client";

import type React from "react";
import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip, type TooltipContentProps } from "recharts";

/**
 * Ported from Monocharts' `MonoRoundedDonutChart`. See `area-chart.tsx` for the
 * shared rationale (data as props, no theme branch, no derived figures, no
 * import of `../dither-charts/lib/recharts-tooltip`).
 *
 * `token` on each slice (e.g. `"--chart-1"`) rather than a literal colour: the
 * caller names which token a slice draws from, and this component reads it —
 * neither side hardcodes a palette, and the five-colour ramp stays the one
 * `globals.css` declares.
 *
 * Upstream computed a `total` from its own const and rendered it as the
 * headline figure, and rendered the hovered slice's own value/name in the
 * donut's centre. Both are gone: a percentage of a total this component never
 * received is exactly the kind of derived figure rule (d) rules out. The
 * centre stays visually empty rather than silently reporting a number nobody
 * gave it.
 */

export type DonutSlice = { label: string; value: number; token: string };

// See area-chart.tsx: TooltipContentProps, not TooltipProps — recharts 3
// moved payload/label/active onto the content-only type. Partial<...>: this
// JSX literal (`<TooltipContent />` below) passes zero props at the call
// site — recharts injects them at runtime via cloneElement — so the bare
// (non-partial) type fails `tsc` on the empty literal even though it's
// correct at runtime. The `!active || !payload` guard is the real protection.
function TooltipContent({ active, payload }: Partial<TooltipContentProps<number, string>>) {
  if (!active || !payload || payload.length === 0) return null;
  const entry = payload[0];
  return (
    <div
      style={{
        background: "var(--surface-raised)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-control)",
        padding: "6px 10px",
        fontSize: "12px",
        lineHeight: 1.4,
      }}
    >
      <div style={{ color: "var(--muted-foreground)" }}>{entry.name}</div>
      <div style={{ color: "var(--foreground)", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
        {entry.value}
      </div>
    </div>
  );
}

export function DonutChart({ data, ariaLabel }: { data: DonutSlice[]; ariaLabel: string }): React.JSX.Element {
  if (data.length === 0) {
    return (
      <div role="img" aria-label={ariaLabel} style={{ color: "var(--muted-foreground)", fontSize: "13px" }}>
        Nothing to show.
      </div>
    );
  }

  return (
    <div role="img" aria-label={ariaLabel} style={{ width: "100%", height: "100%" }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Tooltip content={<TooltipContent />} />
          <Pie
            data={data}
            dataKey="value"
            nameKey="label"
            cx="50%"
            cy="50%"
            innerRadius="46%"
            outerRadius="68%"
            paddingAngle={6}
            cornerRadius={8}
            isAnimationActive={false}
          >
            {data.map((slice) => (
              <Cell key={slice.label} fill={`var(${slice.token})`} stroke="var(--surface-raised)" strokeWidth={2} />
            ))}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
