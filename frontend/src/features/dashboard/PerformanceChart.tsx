import { useEffect, useId, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { scale, smoothPath } from "@/lib/curve";
import { cn } from "@/lib/utils";
import { formatDate, formatNumber } from "@/utils/format";
import type { Feed, Granularity, Series } from "./service";

interface Props {
  loading: boolean;
  error?: string;
  feed?: Feed<Series>;
  granularity: Granularity;
  onGranularity: (value: Granularity) => void;
}

const DEFAULT_WIDTH = 640;
const MIN_WIDTH = 240;
const HEIGHT = 240;
const PAD = { left: 40, right: 16, top: 16, bottom: 32 };

// Solid lines in three clear hues. Colour is never the only cue: each line ends in its own marker shape (circle, square, diamond) and is named in the legend with its latest value.
const SERIES = [
  { key: "requests", label: "Requests sent", tone: "primary", marker: "circle", fillOpacity: 0.26 },
  { key: "accepted", label: "Accepted", tone: "info", marker: "square", fillOpacity: 0.1 },
  { key: "replies", label: "Replies", tone: "accent", marker: "diamond", fillOpacity: 0.1 },
] as const;

function Marker({ kind, x, y, r = 5, className, style }: { kind: (typeof SERIES)[number]["marker"]; x: number; y: number; r?: number; className?: string; style?: React.CSSProperties }) {
  if (kind === "square") return <rect x={x - r} y={y - r} width={r * 2} height={r * 2} rx={1.5} strokeWidth={2} className={className} style={style} />;
  if (kind === "diamond") return <path d={`M${x},${y - r - 1} L${x + r + 1},${y} L${x},${y + r + 1} L${x - r - 1},${y} Z`} strokeWidth={2} strokeLinejoin="round" className={className} style={style} />;
  return <circle cx={x} cy={y} r={r} strokeWidth={2} className={className} style={style} />;
}

/** A date-only value such as 2026-11-02 is a calendar day, not a UTC instant. */
function localDay(date: string): Date {
  const [year, month, day] = date.split("-").map(Number);
  return new Date(year, month - 1, day);
}

export function PerformanceChart({ loading, error, feed, granularity, onGranularity }: Props) {
  return (
    <section aria-labelledby="performance-title" className="grid min-w-0 gap-4 rounded-lg border border-border bg-surface p-4 shadow-raised sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="performance-title" className="text-base font-semibold">
          Performance
        </h2>
        <div role="group" aria-label="Group by" className="flex gap-1 rounded-full bg-surface-muted p-1">
          {(["week", "day"] as const).map((value) => (
            <Button
              key={value}
              size="sm"
              variant="ghost"
              aria-pressed={granularity === value}
              className={cn("rounded-full", granularity === value && "bg-surface text-foreground shadow-raised")}
              onClick={() => onGranularity(value)}
            >
              {value === "week" ? "Weekly" : "Daily"}
            </Button>
          ))}
        </div>
      </div>
      {loading && <Skeleton className="h-60 w-full" />}
      {!loading && error && (
        <p role="alert" className="text-sm text-danger">
          Performance could not be loaded. {error}
        </p>
      )}
      {!loading && !error && feed?.state === "unavailable" && (
        <p className="text-sm text-muted-foreground">
          Performance over time is not available yet. It needs a dashboard feed that is not connected, and Synex will not show a chart without real data.
        </p>
      )}
      {!loading && !error && feed?.state === "ready" && feed.data.points.length === 0 && <p className="text-sm text-muted-foreground">There was no activity in this period.</p>}
      {!loading && !error && feed?.state === "ready" && feed.data.points.length > 0 && <Chart series={feed.data} granularity={granularity} />}
    </section>
  );
}

/** The chart is drawn at the width it is shown at, so its labels keep their real 12px size on a phone. */
function useWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const measure = () => setWidth(Math.max(MIN_WIDTH, Math.round(node.clientWidth)));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return { ref, width };
}

const TONE: Record<(typeof SERIES)[number]["tone"], string> = { primary: "var(--primary)", info: "var(--info)", accent: "var(--accent)" };

function Chart({ series, granularity }: { series: Series; granularity: Granularity }) {
  const { ref, width } = useWidth();
  const fill = useId();
  const [hover, setHover] = useState<number | null>(null);
  const points = series.points;
  const max = Math.max(1, ...points.flatMap((p) => [p.requests, p.accepted, p.replies]));
  const inner = { w: width - PAD.left - PAD.right, h: HEIGHT - PAD.top - PAD.bottom };
  const lines = SERIES.map((line) => {
    const scaled = scale(points.map((p) => p[line.key]), inner.w, inner.h, 0, max).map((point) => ({ x: point.x + PAD.left, y: point.y + PAD.top }));
    return { ...line, scaled, path: smoothPath(scaled) };
  });
  const label = (date: string) => formatDate(localDay(date), "MMM d");
  const summary = `Area chart of requests sent, accepted and replies by ${granularity}, from ${label(points[0].date)} to ${label(points[points.length - 1].date)}. A table with the same data follows.`;
  const base = PAD.top + inner.h;
  const requests = lines[0];
  const areaOf = (line: (typeof lines)[number]) => `${line.path} L${line.scaled[line.scaled.length - 1].x},${base} L${line.scaled[0].x},${base} Z`;
  const ticks = Array.from(new Set([0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(f * (points.length - 1)))));
  const columns = requests.scaled.map((point) => point.x);

  const move = (clientX: number, box: DOMRect) => {
    const x = clientX - box.left;
    let nearest = 0;
    columns.forEach((column, index) => {
      if (Math.abs(column - x) < Math.abs(columns[nearest] - x)) nearest = index;
    });
    setHover(nearest);
  };
  const shown = hover === null ? null : points[hover];
  const tooltipLeft = hover === null ? 0 : Math.min(Math.max(columns[hover] - 80, 0), Math.max(0, width - 168));

  return (
    <div className="grid gap-4">
      <div ref={ref} className="relative min-w-0">
        <svg
          width={width}
          height={HEIGHT}
          viewBox={`0 0 ${width} ${HEIGHT}`}
          role="img"
          aria-label={summary}
          className="block max-w-full touch-pan-y"
          onPointerMove={(event) => move(event.clientX, event.currentTarget.getBoundingClientRect())}
          onPointerLeave={() => setHover(null)}
        >
          <defs>
            {lines.map((line) => (
              <linearGradient key={line.key} id={`${fill}-${line.key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" style={{ stopColor: `rgb(${TONE[line.tone]})`, stopOpacity: line.fillOpacity }} />
                <stop offset="1" style={{ stopColor: `rgb(${TONE[line.tone]})`, stopOpacity: 0 }} />
              </linearGradient>
            ))}
            <filter id={`${fill}-glow`} x="-10%" y="-30%" width="120%" height="160%">
              <feGaussianBlur stdDeviation="3.5" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>
          {[0, 1 / 3, 2 / 3, 1].map((fraction) => {
            const y = PAD.top + (1 - fraction) * inner.h;
            return (
              <g key={fraction}>
                <line x1={PAD.left} x2={width - PAD.right} y1={y} y2={y} className="stroke-border" strokeWidth={1} strokeDasharray={fraction === 0 ? undefined : "3 5"} />
                <text x={PAD.left - 8} y={y + 4} textAnchor="end" className="fill-muted-foreground text-xs tabular-nums">
                  {formatNumber(Math.round(max * fraction))}
                </text>
              </g>
            );
          })}
          {[...lines].reverse().map((line) => <path key={`a-${line.key}`} d={areaOf(line)} fill={`url(#${fill}-${line.key})`} />)}
          {[...lines].reverse().map((line) => (
            <path key={line.key} d={line.path} fill="none" strokeWidth={line.key === "requests" ? 3 : 2.25} strokeLinecap="round" strokeLinejoin="round" filter={line.key === "requests" ? `url(#${fill}-glow)` : undefined} style={{ stroke: `rgb(${TONE[line.tone]})` }} />
          ))}
          {lines.map((line) => (
            <Marker key={`end-${line.key}`} kind={line.marker} x={line.scaled[line.scaled.length - 1].x} y={line.scaled[line.scaled.length - 1].y} className="fill-surface" style={{ stroke: `rgb(${TONE[line.tone]})` }} />
          ))}
          {ticks.map((index) => (
            <text key={index} x={columns[index]} y={HEIGHT - 8} textAnchor={index === 0 ? "start" : index === points.length - 1 ? "end" : "middle"} className="fill-muted-foreground text-xs">
              {label(points[index].date)}
            </text>
          ))}
          {hover !== null && (
            <g>
              <line x1={columns[hover]} x2={columns[hover]} y1={PAD.top} y2={base} className="stroke-border-strong" strokeWidth={1} strokeDasharray="3 4" />
              {lines.map((line) => (
                <Marker key={line.key} kind={line.marker} x={columns[hover]} y={line.scaled[hover].y} r={5} className="fill-surface" style={{ stroke: `rgb(${TONE[line.tone]})`, filter: `drop-shadow(0 0 5px rgb(${TONE[line.tone]} / 0.55))` }} />
              ))}
            </g>
          )}
          {/* One focus stop per period, so the same detail is reachable from the keyboard. */}
          {points.map((point, index) => (
            <circle
              key={point.date}
              cx={columns[index]}
              cy={requests.scaled[index].y}
              r={10}
              fill="transparent"
              tabIndex={0}
              role="img"
              aria-label={`${label(point.date)}: ${point.requests} requests sent, ${point.accepted} accepted, ${point.replies} replies`}
              className="outline-none focus-visible:stroke-ring focus-visible:[stroke-width:2px]"
              onFocus={() => setHover(index)}
              onBlur={() => setHover(null)}
            />
          ))}
        </svg>
        {shown && (
          <div role="presentation" className="pointer-events-none absolute top-2 z-10 w-40 rounded-md border border-border bg-surface p-3 text-xs shadow-float" style={{ left: tooltipLeft }}>
            <p className="mb-1 font-medium text-foreground">{label(shown.date)}</p>
            {SERIES.map((line) => (
              <p key={line.key} className="flex items-center justify-between gap-2 text-muted-foreground">
                <span className="flex items-center gap-1">
                  <span aria-hidden className="size-2 rounded-full" style={{ background: `rgb(${TONE[line.tone]})` }} />
                  {line.label}
                </span>
                <span className="font-medium text-foreground">{formatNumber(shown[line.key])}</span>
              </p>
            ))}
          </div>
        )}
      </div>
      <ul className="flex flex-wrap gap-2 text-sm">
        {SERIES.map((line) => (
          <li key={line.key} className="flex items-center gap-2 rounded-full border border-border bg-surface-muted px-3 py-1">
            <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden className="shrink-0">
              <Marker kind={line.marker} x={7} y={7} r={4} className="fill-surface" style={{ stroke: `rgb(${TONE[line.tone]})` }} />
            </svg>
            <span>{line.label}</span>
            <span className="font-semibold tabular-nums">{formatNumber(points[points.length - 1][line.key])}</span>
          </li>
        ))}
      </ul>
      <details>
        <summary className="w-fit cursor-pointer rounded-sm text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">View the data as a table</summary>
        <div role="region" aria-label="Performance data table" tabIndex={0} className="relative mt-3 overflow-x-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <table className="w-full text-sm">
            <caption className="sr-only">Requests sent, accepted and replies by {granularity}</caption>
            <thead>
              <tr className="border-b border-border text-left text-xs font-medium text-muted-foreground">
                <th scope="col" className="py-2 pr-4">{granularity === "week" ? "Week of" : "Day"}</th>
                <th scope="col" className="py-2 pr-4 text-right">Requests sent</th>
                <th scope="col" className="py-2 pr-4 text-right">Accepted</th>
                <th scope="col" className="py-2 text-right">Replies</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {points.map((p) => (
                <tr key={p.date}>
                  <th scope="row" className="py-2 pr-4 text-left font-normal">{label(p.date)}</th>
                  <td className="py-2 pr-4 text-right">{formatNumber(p.requests)}</td>
                  <td className="py-2 pr-4 text-right">{formatNumber(p.accepted)}</td>
                  <td className="py-2 text-right">{formatNumber(p.replies)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
