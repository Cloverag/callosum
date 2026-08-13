"use client";

import { Card } from "@/components/ui/card";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/vendor/tooltip";
import type { GraphQuality, QualityMetric } from "@/lib/insights";

/**
 * Measured graph quality, replacing an invented aggregate "health %".
 *
 * The tier split is the substance, not decoration. `verified` metrics come from
 * the p1.0.3 mechanism gate: deterministic, no cloud LLM in the loop, identical
 * on every rerun, and CI fails if they regress. `observed` metrics depend on a
 * non-deterministic model and are reported but never gated. A single blended
 * score would hide exactly that distinction, which is the one a research
 * examiner will press on.
 *
 * Form: meters against a fixed 0–100 track. Every bar shares one scale, so bar
 * lengths are comparable across rows — a 50% bar is visibly half a 100% bar.
 * One hue (memory violet), because this is magnitude, not identity.
 */
function MetricRow({ metric }: { metric: QualityMetric }) {
  const pct = metric.total === 0 ? 0 : (metric.value / metric.total) * 100;

  return (
    <div className="py-2">
      <div className="flex items-baseline justify-between gap-3">
        <Tooltip>
          <TooltipTrigger
            className="cursor-help rounded-[4px] text-sm text-muted-foreground underline decoration-dotted decoration-border-strong underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised"
            aria-label={`${metric.label}: ${metric.hint}`}
          >
            {metric.label}
          </TooltipTrigger>
          <TooltipContent side="right" className="max-w-[20rem]">
            {metric.hint}
          </TooltipContent>
        </Tooltip>

        {/* The fraction leads. "17 / 21" is a more honest research claim than
            "81%" alone, because it exposes how small the denominator is. */}
        <span className="shrink-0 text-sm tabular-nums text-foreground">
          {metric.value} / {metric.total}
          <span className="ml-2 text-xs text-subtle-foreground">
            {Math.round(pct)}%
          </span>
        </span>
      </div>

      {/* Fixed 0–100 track so rows are comparable. Hairline track, 4px rounded
          data-end, grown from a single baseline. */}
      <div
        className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-surface-sunken"
        role="img"
        aria-label={`${metric.label}: ${metric.value} of ${metric.total}, ${Math.round(pct)} percent`}
      >
        <div
          className="h-full rounded-full transition-[width] duration-(--duration-state)"
          style={{ width: `${pct}%`, background: "var(--memory)" }}
        />
      </div>
    </div>
  );
}

function Section({
  title,
  caption,
  metrics,
}: {
  title: string;
  caption: string;
  metrics: QualityMetric[];
}) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-subtle-foreground">
        {title}
      </div>
      <p className="mt-1 text-xs text-subtle-foreground">{caption}</p>
      <div className="mt-2">
        {metrics.map((m) => (
          <MetricRow key={m.id} metric={m} />
        ))}
      </div>
    </div>
  );
}

export function GraphQualityPanel({ quality }: { quality: GraphQuality | null }) {
  return (
    <Card className="overflow-hidden">
      <div className="flex items-baseline justify-between gap-4 border-b border-border px-6 py-4">
        <h3 className="text-sm font-semibold text-foreground">Graph quality</h3>
        {quality && (
          <span className="text-xs text-subtle-foreground">
            measured {quality.source.run}
          </span>
        )}
      </div>

      {quality === null ? (
        <div className="grid gap-8 p-6 md:grid-cols-2">
          {Array.from({ length: 2 }).map((_, col) => (
            <div key={col} className="space-y-4">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="space-y-2">
                  <div className="h-4 w-2/3 rounded bg-surface-sunken" />
                  <div className="h-1.5 w-full rounded-full bg-surface-sunken" />
                </div>
              ))}
            </div>
          ))}
        </div>
      ) : (
        <>
          <div className="grid gap-8 p-6 md:grid-cols-2">
            <Section
              title="Verified"
              caption="Deterministic. No language model in the loop — these rerun identically and the build fails if they regress."
              metrics={quality.verified}
            />
            <Section
              title="Observed"
              caption="Depends on the language model, so these are reported and tracked but never used as a gate."
              metrics={quality.observed}
            />
          </div>

          {/* The ablation is the single strongest claim on this card: same
              traversal code, same corpus, same questions — only the grounding
              stage changes. It belongs as a sentence, not another bar. */}
          <div className="border-t border-border bg-surface-alt px-6 py-4">
            <p className="text-xs text-muted-foreground">
              Turning entity grounding off drops answer recall from{" "}
              <span className="tabular-nums text-foreground">{quality.ablation.on}%</span>{" "}
              to{" "}
              <span className="tabular-nums text-foreground">{quality.ablation.off}%</span>{" "}
              on the same graph engine and the same questions — the measured
              contribution of the grounding stage.
            </p>
            <p className="mt-1.5 text-xs text-subtle-foreground">
              Reproduce: {quality.source.files.join(" · ")}
            </p>
          </div>
        </>
      )}
    </Card>
  );
}
