"use client";

import * as React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";
import { transition } from "@/lib/motion";

/**
 * A restrained radial progress ring. One sweep on mount, then still — it reports
 * a share (e.g. verified %), it doesn't perform. Reduced motion renders filled.
 */
export function Gauge({
  value,
  label,
  caption,
  size = 132,
  strokeWidth = 8,
  className,
}: {
  /** 0–100. */
  value: number;
  /** Big centered readout, defaults to `value%`. */
  label?: React.ReactNode;
  /** Small line beneath the readout. */
  caption?: string;
  size?: number;
  strokeWidth?: number;
  className?: string;
}) {
  const reduce = useReducedMotion();
  const clamped = Math.max(0, Math.min(100, value));
  const r = (size - strokeWidth) / 2;
  const c = 2 * Math.PI * r;
  const filled = c * (clamped / 100);

  return (
    <div
      className={cn("relative inline-grid place-items-center", className)}
      style={{ width: size, height: size }}
      role="img"
      aria-label={`${caption ?? "Value"}: ${clamped}%`}
    >
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth={strokeWidth}
          className="text-border"
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          className="text-memory-emphasis"
          strokeDasharray={c}
          initial={{ strokeDashoffset: reduce ? c - filled : c }}
          animate={{ strokeDashoffset: c - filled }}
          /* L5 reveal. The 1.1s and the ease used to be written here; the tier
             was named around this value rather than the value retuned to fit a
             tier, but it now lives in one place with the sparkline and the bar. */
          transition={transition("reveal", reduce)}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">
        <div>
          <div className="text-2xl font-light tabular-nums leading-none text-foreground">
            {label ?? `${clamped}%`}
          </div>
          {caption && <div className="mt-1 text-[10px] font-medium uppercase tracking-[0.08em] text-muted-foreground">{caption}</div>}
        </div>
      </div>
    </div>
  );
}
