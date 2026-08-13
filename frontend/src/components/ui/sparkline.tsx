import { cn } from "@/lib/utils";

/**
 * A minimal trend line — a whisper, not a finance chart. Faint area under a thin
 * stroke, no axes, no grid. Purely indicative; the real number lives beside it.
 * Inherits `currentColor`; on memory surfaces set `text-memory-emphasis`.
 */
export function Sparkline({
  data,
  width = 96,
  height = 28,
  className,
  ariaLabel,
}: {
  data: number[];
  width?: number;
  height?: number;
  className?: string;
  ariaLabel?: string;
}) {
  if (data.length < 2) return null;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const pad = 2;
  const stepX = (width - pad * 2) / (data.length - 1);

  const pts = data.map((v, i) => {
    const x = pad + i * stepX;
    const y = pad + (height - pad * 2) * (1 - (v - min) / span);
    return [x, y] as const;
  });

  const line = pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  const area = `${line} L${pts[pts.length - 1][0].toFixed(1)} ${height} L${pts[0][0].toFixed(1)} ${height} Z`;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={cn("text-memory-emphasis", className)}
      role="img"
      aria-label={ariaLabel}
    >
      {/* L5 reveal, in CSS rather than Framer: this component is not a client
          component and does not need to become one to draw a line once.
          `pathLength={1}` normalises the path so the single dasharray in
          `.reveal-draw` works at any width, data length or value range. */}
      <path d={area} fill="currentColor" fillOpacity={0.1} stroke="none" className="reveal-fade" />
      <path
        d={line}
        pathLength={1}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        className="reveal-draw"
      />
    </svg>
  );
}
