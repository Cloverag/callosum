"use client";

import { useId, useState } from "react";
import { Card } from "@/components/ui/card";
import type { MemoryGrowthPoint } from "@/lib/insights";

/**
 * How institutional memory accumulated, one source document at a time.
 *
 * FORM — contribution bars behind a cumulative line, both for verified edges.
 * The first version plotted edges AND entities as two series; rendered, they sat
 * almost exactly on top of each other (40 vs 38), so the second line cost ink and
 * returned nothing. Entities moved to the tooltip and the table, where the number
 * is still available but is not pretending to be a shape.
 *
 * What replaced it answers a question the cumulative curve alone cannot: WHICH
 * documents actually added memory. The bars make the corpus's design visible —
 * M14 contributes 12 edges, Sales contributes 1 — because the corpus is a
 * capability matrix, not a pile of similar transcripts. Two different quantities,
 * two different marks, one shared scale, no second axis.
 *
 * AXIS — ingestion order, not time. The gold graph has no timestamps, so a date
 * axis would be invented. Ordinal x also makes the real story visible: the curve
 * FLATTENS at Finance/Sales, because those documents mostly mention entities the
 * board meetings already established. A smooth line would have hidden that.
 *
 * Hand-rolled SVG rather than a chart library: ten ordinal points with a shared
 * scale is not what a time-series library is for, and this way the marks obey
 * the design tokens directly — solid hairline grid, no dashes, no theme bridge.
 */

const VIEW_W = 720;
const VIEW_H = 240;
const PAD = { top: 16, right: 16, bottom: 30, left: 34 };

export function MemoryGrowth({ growth }: { growth: MemoryGrowthPoint[] | null }) {
  const clipId = useId();
  const [active, setActive] = useState<number | null>(null);

  const ready = growth !== null && growth.length > 1;
  if (!ready) {
    return (
      <Card className="overflow-hidden">
        <div className="border-b border-border px-6 py-4">
          <h3 className="text-sm font-semibold text-foreground">Memory growth</h3>
        </div>
        <div className="p-6">
          <div className="h-[200px] w-full rounded-[12px] bg-surface-sunken" />
        </div>
      </Card>
    );
  }

  const points = growth;
  const last = points[points.length - 1];

  // One shared scale for both series — they are the same kind of thing (counts),
  // so a second axis would invent a correlation that is not in the data.
  const maxY = Math.max(...points.map((p) => Math.max(p.edges, p.entities)));
  const niceMax = Math.ceil(maxY / 10) * 10;
  const plotW = VIEW_W - PAD.left - PAD.right;
  const plotH = VIEW_H - PAD.top - PAD.bottom;

  const x = (i: number) => PAD.left + (plotW * i) / (points.length - 1);
  const y = (v: number) => PAD.top + plotH * (1 - v / niceMax);

  const line = (key: "edges" | "entities") =>
    points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)} ${y(p[key]).toFixed(1)}`).join(" ");

  /** What each document added on its own — the cumulative series differenced. */
  const added = points.map((p, i) => (i === 0 ? p.edges : p.edges - points[i - 1].edges));
  const band = plotW / (points.length - 1);
  const barW = Math.min(22, band * 0.5); // capped: never fill the slot, leave air

  const ticks = [0, niceMax / 2, niceMax];
  const hovered = active === null ? null : points[active];

  return (
    <Card className="overflow-hidden">
      <div className="flex items-baseline justify-between gap-4 border-b border-border px-6 py-4">
        <h3 className="text-sm font-semibold text-foreground">Memory growth</h3>
        <span className="text-xs text-muted-foreground">
          <span className="tabular-nums text-foreground">{points.length}</span> documents ingested
        </span>
      </div>

      <div className="px-4 pb-4 pt-5">
        <div className="relative">
          <svg
            viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
            className="w-full"
            role="img"
            aria-label={`Cumulative graph growth across ${points.length} documents, ending at ${last.edges} verified edges and ${last.entities} entities.`}
            onMouseLeave={() => setActive(null)}
          >
            <defs>
              <clipPath id={clipId}>
                <rect x={PAD.left} y={PAD.top} width={plotW} height={plotH} />
              </clipPath>
            </defs>

            {/* Grid — solid hairlines one step off the surface, never dashed. */}
            {ticks.map((t) => (
              <g key={t}>
                <line
                  x1={PAD.left}
                  x2={VIEW_W - PAD.right}
                  y1={y(t)}
                  y2={y(t)}
                  stroke="var(--border)"
                  strokeWidth={1}
                />
                <text
                  x={PAD.left - 8}
                  y={y(t) + 4}
                  textAnchor="end"
                  className="fill-[var(--subtle-foreground)] text-[11px] tabular-nums"
                >
                  {t}
                </text>
              </g>
            ))}

            {/* Per-document contribution. Quiet fill so the cumulative line
                stays the figure and these stay the ground. Rounded data-end,
                square at the baseline, grown from one baseline. */}
            {points.map((p, i) => {
              const h = y(0) - y(added[i]);
              if (h <= 0) return null;
              return (
                <rect
                  key={p.document}
                  x={x(i) - barW / 2}
                  y={y(added[i])}
                  width={barW}
                  height={h}
                  rx={3}
                  fill="var(--memory)"
                  fillOpacity={active === i ? 0.34 : 0.16}
                />
              );
            })}

            {/* Cumulative verified edges — the figure. */}
            <path
              d={line("edges")}
              fill="none"
              stroke="var(--memory)"
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              clipPath={`url(#${clipId})`}
            />

            {/* Endpoint marker with a 2px surface ring. */}
            <circle cx={x(points.length - 1)} cy={y(last.edges)} r={4}
              fill="var(--memory)" stroke="var(--surface-raised)" strokeWidth={2} />

            {/* Crosshair + hovered points. */}
            {active !== null && hovered && (
              <g pointerEvents="none">
                <line
                  x1={x(active)} x2={x(active)} y1={PAD.top} y2={PAD.top + plotH}
                  stroke="var(--border-strong)" strokeWidth={1}
                />
                <circle cx={x(active)} cy={y(hovered.edges)} r={4}
                  fill="var(--memory)" stroke="var(--surface-raised)" strokeWidth={2} />
              </g>
            )}

            {/* Axis labels — only the ends, so ten labels never collide. */}
            <text x={PAD.left} y={VIEW_H - 8}
              className="fill-[var(--subtle-foreground)] text-[11px]">
              {points[0].label}
            </text>
            <text x={VIEW_W - PAD.right} y={VIEW_H - 8} textAnchor="end"
              className="fill-[var(--subtle-foreground)] text-[11px]">
              {last.label}
            </text>

            {/* Hit targets, wider than the marks. */}
            {points.map((p, i) => (
              <rect
                key={p.document}
                x={x(i) - plotW / (points.length - 1) / 2}
                y={PAD.top}
                width={plotW / (points.length - 1)}
                height={plotH}
                fill="transparent"
                onMouseEnter={() => setActive(i)}
              />
            ))}
          </svg>

          {/* Tooltip — a neutral dark bubble; blue is ACTION only and a readout
              is not an action. */}
          {hovered && (
            <div
              className="pointer-events-none absolute top-2 rounded-[8px] bg-foreground px-3 py-2 text-xs text-surface-raised shadow-overlay"
              style={{
                left: `${(x(active!) / VIEW_W) * 100}%`,
                transform:
                  active! > points.length / 2 ? "translateX(-104%)" : "translateX(4%)",
              }}
            >
              <div className="font-medium">{hovered.label}</div>
              <div className="mt-1 tabular-nums text-border-strong">
                +{added[active!]} edges · {hovered.edges} total
              </div>
              <div className="tabular-nums text-border-strong">
                {hovered.entities} entities
              </div>
            </div>
          )}
        </div>

        {/* Legend, doubling as the direct label by carrying each series' final
            value. Identity rests on name, value and mark shape — never hue alone.
            Text stays in ink tokens; only the swatch is coloured. */}
        <div className="mt-1 flex items-center gap-6 px-2 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-2">
            <span className="h-0.5 w-3 rounded-full" style={{ background: "var(--memory)" }} aria-hidden />
            Verified edges, cumulative
            <span className="tabular-nums text-foreground">{last.edges}</span>
          </span>
          <span className="inline-flex items-center gap-2">
            <span
              className="h-2.5 w-2 rounded-[2px]"
              style={{ background: "color-mix(in srgb, var(--memory) 16%, transparent)" }}
              aria-hidden
            />
            Added per document
          </span>
        </div>

        <details className="mt-3 px-2">
          <summary className="cursor-pointer text-xs text-muted-foreground underline decoration-dotted underline-offset-4 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised">
            View as table
          </summary>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full min-w-[22rem] text-xs">
              <caption className="sr-only">
                Cumulative verified edges and entities after each document is ingested
              </caption>
              <thead>
                <tr className="text-left text-subtle-foreground">
                  <th scope="col" className="py-1 font-medium">Document</th>
                  <th scope="col" className="py-1 text-right font-medium">Added</th>
                  <th scope="col" className="py-1 text-right font-medium">Edges</th>
                  <th scope="col" className="py-1 text-right font-medium">Entities</th>
                </tr>
              </thead>
              <tbody className="text-muted-foreground">
                {points.map((p, i) => (
                  <tr key={p.document} className="border-t border-border">
                    <td className="py-1">{p.label}</td>
                    <td className="py-1 text-right tabular-nums">+{added[i]}</td>
                    <td className="py-1 text-right tabular-nums text-foreground">{p.edges}</td>
                    <td className="py-1 text-right tabular-nums">{p.entities}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </div>
    </Card>
  );
}
