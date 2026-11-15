import type { Feed, Series } from "./service";

export type SeriesKey = "requests" | "accepted" | "replies";

/** The points of a feed that is available, or none. Nothing is ever filled in. */
export function pointsOf(feed: Feed<Series> | undefined): Series["points"] {
  return feed?.state === "ready" ? feed.data.points : [];
}

export const valuesOf = (points: Series["points"], key: SeriesKey): number[] => points.map((point) => point[key]);

export interface Change {
  /** Latest period minus the one before it. */
  delta: number;
  /** As a share of the previous period, or null when the previous period was zero. */
  percent: number | null;
}

/** How the latest period compares with the one before it. Needs two periods; otherwise there is no trend to show. */
export function changeOf(values: number[]): Change | null {
  if (values.length < 2) return null;
  const latest = values[values.length - 1];
  const previous = values[values.length - 2];
  return { delta: latest - previous, percent: previous === 0 ? null : ((latest - previous) / previous) * 100 };
}

/** Reply rate per period, as a percentage, for periods that sent something. */
export function replyRates(points: Series["points"]): number[] {
  return points.filter((point) => point.requests > 0).map((point) => (point.replies / point.requests) * 100);
}

export function describeChange(change: Change, unit: "weekly" | "daily", suffix = ""): string {
  const sign = change.delta > 0 ? "+" : change.delta < 0 ? "−" : "";
  const size = Math.abs(change.delta);
  const amount = Number.isInteger(size) ? String(size) : size.toFixed(1);
  const percent = change.percent === null ? "" : ` (${sign}${Math.abs(Math.round(change.percent))}%)`;
  return `${sign}${amount}${suffix}${percent} vs previous ${unit === "weekly" ? "week" : "day"}`;
}

export function greetingFor(date: Date): string {
  const hour = date.getHours();
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}
