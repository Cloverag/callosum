"use client";

import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { Gauge } from "@/components/ui/gauge";
import { Sparkline } from "@/components/ui/sparkline";
import { StatBar, type StatSegment } from "@/components/ui/stat-bar";
import type { MemoryHealth as MemoryHealthData } from "@/lib/insights";

/** A compact label/value row. `dot` marks quality categories; `tone` tints the label. */
function Row({ label, value, dot, tone }: { label: string; value: string; dot?: string; tone?: string }) {
  return (
    <div className="flex items-center justify-between py-1.5 text-sm">
      <span className={cn("inline-flex items-center gap-2", tone ?? "text-muted-foreground")}>
        {dot && <span className={cn("size-1.5 rounded-full", dot)} aria-hidden />}
        {label}
      </span>
      <span className="tabular-nums text-foreground">{value}</span>
    </div>
  );
}

export function MemoryHealth({
  memory,
  reviewVelocity,
  statusSegments,
}: {
  memory: MemoryHealthData | null;
  reviewVelocity: number[] | null;
  statusSegments: StatSegment[];
}) {
  return (
    <Card className="overflow-hidden">
      <div className="border-b border-border px-6 py-4">
        <h3 className="text-sm font-semibold text-foreground">Graph health</h3>
      </div>

      {memory === null ? (
        <div className="grid gap-6 p-6 md:grid-cols-3">
          <div className="mx-auto size-[132px] rounded-full bg-surface-sunken" />
          <div className="space-y-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-4 w-full rounded bg-surface-sunken" />
            ))}
          </div>
          <div className="space-y-6">
            <div className="h-8 w-full rounded bg-surface-sunken" />
            <div className="h-8 w-full rounded bg-surface-sunken" />
          </div>
        </div>
      ) : (
        <div className="grid gap-x-8 gap-y-6 p-6 md:grid-cols-3">
          {/* Centerpiece: verified share */}
          <div className="flex flex-col items-center justify-center">
            <Gauge value={memory.verifiedPct} caption="Verified" size={150} strokeWidth={9} />
            <p className="mt-3 max-w-[16rem] text-center text-xs text-muted-foreground">
              Every graph edge carries a located source quote.
            </p>
          </div>

          {/* Quality before quantity */}
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-subtle-foreground">Quality</div>
            <div className="mt-1">
              <Row label="Verified" value={`${memory.verifiedPct}%`} dot="bg-success" tone="text-success-emphasis" />
              <Row label="Pending review" value={String(memory.pendingReview)} dot="bg-warning" tone="text-warning-emphasis" />
              <Row label="Quarantined" value={String(memory.quarantined)} dot="bg-danger" tone="text-danger-emphasis" />
            </div>
            <div className="mt-4 text-[10px] font-semibold uppercase tracking-[0.08em] text-subtle-foreground">Coverage</div>
            <div className="mt-1">
              <Row label="Entities" value={memory.entities.toLocaleString()} />
              <Row label="Edges" value={memory.edges.toLocaleString()} />
              <Row label="Communities" value={String(memory.communities)} />
            </div>
          </div>

          {/* Trends */}
          <div className="space-y-6">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Review throughput</span>
                {reviewVelocity && reviewVelocity.length > 0 && (
                  <span className="text-sm tabular-nums text-foreground">{reviewVelocity[reviewVelocity.length - 1]}/wk</span>
                )}
              </div>
              {reviewVelocity && (
                <Sparkline
                  data={reviewVelocity}
                  width={220}
                  height={36}
                  className="mt-2 w-full"
                  ariaLabel="Weekly review throughput, trending up"
                />
              )}
              <p className="mt-1 text-xs text-subtle-foreground">last 8 weeks</p>
            </div>

            <div>
              <span className="text-sm text-muted-foreground">Meeting mix</span>
              <StatBar segments={statusSegments} className="mt-2" ariaLabel="Meetings by status" />
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
