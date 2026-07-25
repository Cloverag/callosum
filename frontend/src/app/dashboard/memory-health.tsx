"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { Gauge } from "@/components/ui/gauge";
import { Sparkline } from "@/components/ui/sparkline";
import { StatBar, type StatSegment } from "@/components/ui/stat-bar";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/animate-ui/components/radix/tooltip";
import type { MemoryHealth as MemoryHealthData } from "@/lib/insights";

/**
 * A compact label/value row. `dot` marks quality categories; `tone` tints the label.
 * When `hint` is given the label becomes a tooltip trigger — these are Callosum
 * terms of art ("quarantined" is not standard board vocabulary), and the whole
 * point of the card is that a non-technical director can trust what it says.
 */
function Row({
  label,
  value,
  dot,
  tone,
  hint,
}: {
  label: string;
  value: string;
  dot?: string;
  tone?: string;
  hint?: string;
}) {
  const labelEl = (
    <span className={cn("inline-flex items-center gap-2", tone ?? "text-muted-foreground")}>
      {dot && <span className={cn("size-1.5 rounded-full", dot)} aria-hidden />}
      {label}
    </span>
  );

  return (
    <div className="flex items-center justify-between py-1.5 text-sm">
      {hint ? (
        <Tooltip>
          {/* Dotted underline so the affordance is visible without hovering, and
              a button so it is keyboard-reachable — hover alone would hide this
              from anyone not using a mouse. */}
          <TooltipTrigger
            className="cursor-help rounded-[4px] underline decoration-dotted decoration-border-strong underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised"
            aria-label={`${label}: ${hint}`}
          >
            {labelEl}
          </TooltipTrigger>
          <TooltipContent side="right" className="max-w-[15rem]">
            {hint}
          </TooltipContent>
        </Tooltip>
      ) : (
        labelEl
      )}
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
      <div className="flex items-baseline justify-between gap-4 border-b border-border px-6 py-4">
        <h3 className="text-sm font-semibold text-foreground">Graph health</h3>
        {/* The band reports on the graph; until now there was no way to reach it. */}
        <Link
          href="/memory"
          className="rounded-[6px] text-xs text-accent-emphasis hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised"
        >
          View the graph →
        </Link>
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
              <Row
                label="Verified"
                value={`${memory.verifiedPct}%`}
                dot="bg-success"
                tone="text-success-emphasis"
                hint="Share of graph edges whose evidence quote was located verbatim in the source document. An edge cannot exist without one."
              />
              <Row
                label="Pending review"
                value={String(memory.pendingReview)}
                dot="bg-warning"
                tone="text-warning-emphasis"
                hint="Facts that passed verification and are waiting for a human to approve them. Nothing enters memory unapproved."
              />
              <Row
                label="Quarantined"
                value={String(memory.quarantined)}
                dot="bg-danger"
                tone="text-danger-emphasis"
                hint="Extractions the verifier rejected — kept, not deleted, so the failures stay auditable."
              />
            </div>
            <div className="mt-4 text-[10px] font-semibold uppercase tracking-[0.08em] text-subtle-foreground">Coverage</div>
            <div className="mt-1">
              <Row label="Documents" value={String(memory.documents)} />
              <Row label="Entities" value={memory.entities.toLocaleString()} />
              <Row label="Edges" value={memory.edges.toLocaleString()} />
              <Row
                label="Relation types"
                value={String(memory.relationTypes)}
                hint="Distinct ontology relations actually present in the graph — APPROVED, OPPOSED, SUPERSEDES, ALIAS_OF and the rest."
              />
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
