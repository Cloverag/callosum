"use client";

import type React from "react";
import { useId } from "react";
import {
  ResponsiveContainer,
  AreaChart as RechartsAreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  type TooltipContentProps,
} from "recharts";

/**
 * Ported from Monocharts' `MonoRoundedAreaChart`
 * (github.com/Subhan-code/Monocharts, `src/components/mono-charts/`).
 *
 * ---------------------------------------------------------------------------
 * WHAT CHANGED FROM UPSTREAM, AND WHY
 * ---------------------------------------------------------------------------
 * - The module-level `MONO_AREA_DATA` const is gone. Data is a prop. A chart
 *   component holding its own numbers is the same hazard `src/demo/` exists to
 *   rule out for the rest of the app — see `__tests__/demo-mode.test.ts`.
 * - The `theme?: 'dark' | 'light'` prop and every `isDark` branch are gone.
 *   Every colour below is a `var(--token)` read from `globals.css`, which
 *   already flips with the theme; there was nothing left to branch on.
 * - The headline "peak throughput" figure — upstream read it off the last
 *   point in its own const — is gone with the const. This component renders
 *   what it is given and computes nothing: no total, no percentage, no "latest
 *   value" callout derived from `data`.
 * - Upstream's tooltip imported `DitherChartTooltipContent` from a sibling
 *   directory (`../dither-charts/lib/recharts-tooltip`) that was never part of
 *   this port and carried its own `theme` prop — reintroducing it would have
 *   smuggled back the exact thing the point above removes. This uses
 *   recharts' own `<Tooltip />`, styled inline from the same tokens.
 * - Curve toggle, gradient-fill `<defs>`, header/footer chrome, hover states —
 *   all upstream presentation, not part of the four-prop contract this was
 *   ported to. Composition (sizing, placement, chrome) is the caller's job.
 */

export type AreaPoint = { label: string; value: number };

/**
 * `TooltipContentProps`, not `TooltipProps` — recharts 3 moved `payload`,
 * `label` and `active` off `TooltipProps` onto a wrapper type
 * (`type PropertiesReadFromContext` in `recharts/types/component/Tooltip.d.ts`)
 * because a `<Tooltip>` now reads them from context rather than receiving them
 * as props. A custom `content` render function still gets them — just typed
 * one level down.
 *
 * `Partial<...>`, not the bare type: `<Tooltip content={<TooltipContent />} />`
 * below passes zero props at the JSX call site — recharts injects `active`/
 * `payload`/`label`/etc. itself at runtime via `React.cloneElement`, they never
 * appear in source. `TooltipContentProps` marks those fields required, so the
 * bare type made the empty-props literal fail `tsc` even though it's correct
 * at runtime. `Partial` matches what's actually being declared here; the
 * `!active || !payload` guard below is what actually protects the render.
 */
function TooltipContent({ active, payload, label }: Partial<TooltipContentProps<number, string>>) {
  if (!active || !payload || payload.length === 0) return null;
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
      <div style={{ color: "var(--muted-foreground)" }}>{label}</div>
      <div style={{ color: "var(--foreground)", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
        {payload[0]?.value}
      </div>
    </div>
  );
}

export function AreaChart({ data, ariaLabel }: { data: AreaPoint[]; ariaLabel: string }): React.JSX.Element {
  // useId(), not a literal string: two <AreaChart>s on one page would
  // otherwise both emit id="meridian-area-fill", an invalid duplicate id
  // where `url(#...)` resolves to the first match in document order — the
  // second chart silently paints with the first chart's gradient. useId()
  // is unique per component instance and stable across SSR/hydration,
  // unlike Math.random() or a module-level counter.
  const gradientId = useId();

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
        <RechartsAreaChart data={data} margin={{ top: 12, right: 12, left: -22, bottom: 0 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.35} />
              <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="2 2" vertical={false} stroke="var(--border)" />
          <XAxis
            dataKey="label"
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
          />
          <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
          <Tooltip content={<TooltipContent />} />
          <Area
            type="monotone"
            dataKey="value"
            stroke="var(--chart-1)"
            strokeWidth={2.5}
            strokeLinecap="round"
            strokeLinejoin="round"
            fill={`url(#${gradientId})`}
            isAnimationActive={false}
          />
        </RechartsAreaChart>
      </ResponsiveContainer>
    </div>
  );
}
