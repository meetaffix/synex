import { useId } from "react";
import { scale, smoothPath } from "@/lib/curve";
import { cn } from "@/lib/utils";

/** A tiny trend line. Decorative: the figure beside it carries the meaning. Needs at least two points to draw. */
export function Sparkline({ values, width = 96, height = 32, tone = "primary", className }: { values: number[]; width?: number; height?: number; tone?: "primary" | "accent" | "info" | "brand"; className?: string }) {
  const gradient = useId();
  if (values.length < 2) return null;
  const points = scale(values, width, height, 3);
  const line = smoothPath(points);
  const area = `${line} L${points[points.length - 1].x},${height} L${points[0].x},${height} Z`;
  const colour = { primary: "var(--primary)", accent: "var(--accent)", info: "var(--info)", brand: "var(--brand-accent)" }[tone];
  const last = points[points.length - 1];
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden className={cn("shrink-0 overflow-visible", className)}>
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" style={{ stopColor: `rgb(${colour})`, stopOpacity: 0.28 }} />
          <stop offset="1" style={{ stopColor: `rgb(${colour})`, stopOpacity: 0 }} />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gradient})`} />
      <path d={line} fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ stroke: `rgb(${colour})` }} />
      <circle cx={last.x} cy={last.y} r="3" style={{ fill: `rgb(${colour})` }} />
    </svg>
  );
}
